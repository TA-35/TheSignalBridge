#!/bin/bash
# Serve Compose from the uni GPU server. Run there as ubuntu:
#
#     bash uni_compose.sh <port>            # 127.0.0.1 only: test it first
#     bash uni_compose.sh <port> --public   # 0.0.0.0, once eSolutions routes HTTPS to <port>
#
# Two services that start on boot and restart if they stop:
#   compose-llm      llama-server with the fine-tuned model (run 2) on the GPU,
#                    127.0.0.1:8080 - never reachable from outside
#   compose-service  the inference service (classifiers, prompt, model,
#                    grounding check) on <port>
#
# Every endpoint but /health needs "Authorization: Bearer <token>", the token
# in ~/.compose_token (made here on first run). The AWS inference box sends it
# as COMPOSE_REMOTE_TOKEN. See README.md for the whole cutover. Safe to run again.
set -euo pipefail

PORT=${1:?usage: bash uni_compose.sh <port> [--public]}
BIND=127.0.0.1
[ "${2:-}" = "--public" ] && BIND=0.0.0.0
REPO=$HOME/signalbridge
VENV=$HOME/compose-venv
LLAMA=$HOME/llama.cpp-cuda/build/bin/llama-server
MODEL=$HOME/models/compose/run2.Q4_K_M.gguf
MODEL_SHA256=34bd38e558a4ea6ea0df7a342274beb1ca1edfa5aaaef1596c77e388e4fcffdd
PROMPT_FINGERPRINT=675475a8cd29
TOKEN_FILE=$HOME/.compose_token
ENV_FILE=$HOME/.compose_service.env

fail() { echo "not ready: $1"; exit 1; }
nvidia-smi >/dev/null 2>&1 || fail "no GPU (nvidia-smi)"
[ -x "$LLAMA" ] || fail "no CUDA llama-server at $LLAMA"
[ -f "$MODEL" ] || fail "model missing: $MODEL"
echo "$MODEL_SHA256  $MODEL" | sha256sum -c --quiet - || fail "$MODEL is not run 2 (sha256 differs)"
"$VENV/bin/python" -c "import gunicorn, flask, spacy, torch, transformers, sentence_transformers, en_core_web_sm" \
  2>/dev/null || fail "$VENV is missing packages (requirements.txt + requirements-compose.txt)"
[ -f "$REPO/models/enron_register_distilbert/model.safetensors" ] || fail "tone weights missing under $REPO/models"
# Hugging Face is blocked on this network: the NLI model has to be copied in.
[ -d "$HOME/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base" ] || fail "NLI model not cached"
(cd "$REPO" && "$VENV/bin/python" -c "from Src.source.pipeline import compose_prompt as cp; \
assert cp.fingerprint() == '$PROMPT_FINGERPRINT', cp.fingerprint()") || fail "prompt is not the one run 2 was trained on"
grep -q PIPELINE_SERVICE_TOKEN "$REPO/Src/source/pipeline/service.py" \
  || fail "the code in $REPO has no token check - sync main before serving"

if [ ! -s "$TOKEN_FILE" ]; then
  (umask 077; openssl rand -hex 32 > "$TOKEN_FILE")
  echo "made a new token in $TOKEN_FILE"
fi
(umask 077; printf 'PIPELINE_SERVICE_TOKEN=%s\n' "$(cat "$TOKEN_FILE")" > "$ENV_FILE")

sudo tee /etc/systemd/system/compose-llm.service >/dev/null <<EOF
[Unit]
Description=Compose rewrite model (llama-server, fine-tuned run 2, GPU)
After=network-online.target

[Service]
User=$USER
ExecStart=$LLAMA -m $MODEL --jinja --chat-template-kwargs '{"enable_thinking":false}' --host 127.0.0.1 --port 8080 -c 16384 -ngl 99
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/compose-service.service >/dev/null <<EOF
[Unit]
Description=Compose service (classifiers, prompt, model, grounding check)
After=network-online.target compose-llm.service
Wants=compose-llm.service

[Service]
User=$USER
WorkingDirectory=$REPO
EnvironmentFile=$ENV_FILE
Environment=COMPOSE_LLM_URL=http://127.0.0.1:8080
Environment=COMPOSE_MODEL_NAME=qwen3.5-4b-ft-run2
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
# One worker: each one loads every model. Threads serve concurrent requests.
ExecStart=$VENV/bin/gunicorn --workers 1 --threads 4 --timeout 120 --bind $BIND:$PORT 'Src.source.pipeline.service:create_service()'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

pkill -u "$USER" -x llama-server || true     # a hand-started test server would hold :8080
sleep 2
sudo systemctl daemon-reload
sudo systemctl enable --now compose-llm compose-service
sudo systemctl restart compose-llm compose-service     # pick up a changed unit on a re-run

echo "waiting for the model and the service to load..."
for _ in $(seq 1 90); do curl -s -m 2 "127.0.0.1:$PORT/health" | grep -q '"enabled":true' && break; sleep 2; done
curl -s "127.0.0.1:$PORT/health"; echo
start=$(date +%s)
reply=$(curl -s -m 100 -X POST "127.0.0.1:$PORT/compose" -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H 'Content-Type: application/json' -d '{"message":"could you send me the Q3 report by Friday?"}')
echo "test rewrite in $(( $(date +%s) - start ))s: $(echo "$reply" | grep -o '"degraded":[a-z]*')"
echo "unauthenticated: HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST "127.0.0.1:$PORT/compose" \
  -H 'Content-Type: application/json' -d '{"message":"x"}') (should be 401)"
systemctl --no-pager is-active compose-llm compose-service
echo "listening on $BIND:$PORT"
