#!/bin/bash
# Run once on the uni GPU server, as ubuntu, after aws_tunnel_endpoint.sh has
# run on the AWS inference box:
#
#     bash uni_services.sh <inference box Elastic IP>
#
# Sets up three services that start on boot and restart if they stop. All
# three listen on 127.0.0.1 only; nothing here is reachable from outside.
#   compose-llm      llama-server with the fine-tuned model on the GPU, :8080
#   compose-service  the inference service with Compose on (classifiers,
#                    prompt, model, grounding check), :8100
#   compose-tunnel   connects out to the AWS inference box on port 443 and
#                    forwards 127.0.0.1:18100 there to :8100 here
#
# Expects the repo at ~/signalbridge (Src/ and models/, with the tone model's
# weights) and a venv at ~/compose-venv with requirements.txt and
# requirements-compose.txt installed. Hugging Face is blocked on this network,
# so the NLI model has to be in ~/.cache/huggingface already. Safe to run again.
set -euo pipefail

AWS_HOST=${1:?usage: bash uni_services.sh <inference box Elastic IP>}
REPO=$HOME/signalbridge
VENV=$HOME/compose-venv
LLAMA=$HOME/llama.cpp-cuda/build/bin/llama-server
MODEL=$HOME/models/compose/run1.Q4_K_M.gguf
KEY=$HOME/.ssh/llm_tunnel_ed25519
KNOWN=$HOME/.ssh/llm_tunnel_known_hosts
# The inference box's own SSH host key (checked over Instance Connect). The
# tunnel only ever connects to the machine holding this key.
HOST_KEY_FP='SHA256:BQkkLIxDGoWFO0oDeYR1TM56rqfYjBT6ctWQ24x5pO4'

[ -x "$LLAMA" ] || { echo "no GPU llama-server at $LLAMA - has the CUDA build finished?"; exit 1; }
[ -f "$MODEL" ] || { echo "model missing: $MODEL"; exit 1; }
[ -f "$KEY" ] || { echo "tunnel key missing: $KEY"; exit 1; }
"$VENV/bin/python" -c "import gunicorn, flask, spacy, torch, transformers, sentence_transformers" 2>/dev/null \
  || { echo "the venv at $VENV is missing packages - is the pip install finished?"; exit 1; }
[ -f "$REPO/models/enron_register_distilbert/model.safetensors" ] || { echo "tone weights missing under $REPO/models"; exit 1; }

ssh-keyscan -p 443 -t ed25519 "$AWS_HOST" 2>/dev/null > "$KNOWN"
if ! ssh-keygen -l -f "$KNOWN" | grep -q "$HOST_KEY_FP"; then
  echo "host key on $AWS_HOST:443 is not the inference box's ($HOST_KEY_FP) - stopping"
  rm -f "$KNOWN"
  exit 1
fi

sudo tee /etc/systemd/system/compose-llm.service >/dev/null <<EOF
[Unit]
Description=Compose rewrite model (llama-server, fine-tuned run 1, GPU)
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
Environment=COMPOSE_LLM_URL=http://127.0.0.1:8080
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
# One worker: each one loads every model. Threads serve concurrent requests.
ExecStart=$VENV/bin/gunicorn --workers 1 --threads 4 --timeout 120 --bind 127.0.0.1:8100 'Src.source.pipeline.service:create_service()'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/compose-tunnel.service >/dev/null <<EOF
[Unit]
Description=Forward the Compose service to the AWS inference box ($AWS_HOST)
After=network-online.target compose-service.service
Wants=network-online.target

[Service]
User=$USER
ExecStart=/usr/bin/ssh -N -p 443 -i $KEY -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$KNOWN -R 127.0.0.1:18100:127.0.0.1:8100 llmtunnel@$AWS_HOST
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Anything started by hand for testing would hold the ports.
pkill -u "$USER" -x llama-server || true
sleep 2

sudo systemctl daemon-reload
sudo systemctl enable --now compose-llm compose-service compose-tunnel
echo "waiting for the model and the service to load..."
for _ in $(seq 1 90); do curl -s -m 2 127.0.0.1:8100/health | grep -q '"enabled":true' && break; sleep 2; done
curl -s 127.0.0.1:8100/health; echo
systemctl --no-pager is-active compose-llm compose-service compose-tunnel
