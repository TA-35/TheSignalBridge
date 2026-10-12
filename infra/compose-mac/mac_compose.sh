#!/bin/bash
# Serve Compose from this Mac while the uni GPU server has no HTTPS route.
# Run as yourself, not with sudo:
#
#     bash infra/compose-mac/mac_compose.sh start
#     bash infra/compose-mac/mac_compose.sh status
#     bash infra/compose-mac/mac_compose.sh stop
#
# The same two services as infra/compose-uni/uni_compose.sh, as launchd agents
# instead of systemd units. Both start at login, restart if they stop, and
# listen on 127.0.0.1 only:
#   com.signalbridge.compose-llm      llama-server with run 2 on Metal, :8080,
#                                     inside caffeinate so the Mac stays awake
#   com.signalbridge.compose-service  the inference service (classifiers,
#                                     prompt, model, grounding check), :8101
#
# Tailscale Funnel publishes :8101 over HTTPS - README.md has the steps and the
# AWS cutover. Every endpoint but /health needs "Authorization: Bearer <token>",
# the token in ~/.compose_token (made on first start). Safe to run again.
#
# Paths default to this checkout. Override them when the model or the Python
# environment live elsewhere:
#   COMPOSE_MODEL  run 2's GGUF (default <repo>/models/compose_run2/qwen35-4b-compose-run2.Q4_K_M.gguf)
#   COMPOSE_VENV   a venv with requirements.txt + requirements-compose.txt (default <repo>/backend/.venv)
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../.." && pwd)
MODEL=${COMPOSE_MODEL:-$REPO/models/compose_run2/qwen35-4b-compose-run2.Q4_K_M.gguf}
VENV=${COMPOSE_VENV:-$REPO/backend/.venv}
LLAMA=$(command -v llama-server || true)
MODEL_SHA256=34bd38e558a4ea6ea0df7a342274beb1ca1edfa5aaaef1596c77e388e4fcffdd
PROMPT_FINGERPRINT=675475a8cd29
LLM_PORT=8080
PORT=8101
TOKEN_FILE=$HOME/.compose_token
AGENTS=$HOME/Library/LaunchAgents
LOGS=$HOME/Library/Logs/signalbridge
LLM_LABEL=com.signalbridge.compose-llm
SVC_LABEL=com.signalbridge.compose-service
DOMAIN=gui/$(id -u)

fail() { echo "not ready: $1"; exit 1; }

stop() {
  for label in $SVC_LABEL $LLM_LABEL; do
    if launchctl bootout "$DOMAIN/$label" 2>/dev/null; then
      # bootout returns while the process is still exiting, and bootstrapping
      # the label again before launchd lets go of it fails with an I/O error.
      for _ in $(seq 1 30); do launchctl print "$DOMAIN/$label" >/dev/null 2>&1 || break; sleep 1; done
      echo "stopped $label"
    fi
    rm -f "$AGENTS/$label.plist"
  done
}

status() {
  for label in $LLM_LABEL $SVC_LABEL; do
    state=$(launchctl print "$DOMAIN/$label" 2>/dev/null | awk '/^\tstate = / {print $3; exit}' || true)
    echo "$label: ${state:-not loaded}"
  done
  echo "health: $(curl -s -m 3 "127.0.0.1:$PORT/health" || echo "no answer on 127.0.0.1:$PORT")"
  if command -v tailscale >/dev/null; then tailscale funnel status 2>/dev/null || true; fi
}

start() {
  [ "$(uname)" = Darwin ] || fail "this is the Mac script; the uni server uses infra/compose-uni/uni_compose.sh"
  [ -n "$LLAMA" ] || fail "no llama-server on PATH (brew install llama.cpp)"
  [ -f "$MODEL" ] || fail "model missing: $MODEL (set COMPOSE_MODEL)"
  echo "checking the model..."
  [ "$(shasum -a 256 "$MODEL" | cut -d' ' -f1)" = "$MODEL_SHA256" ] || fail "$MODEL is not run 2 (sha256 differs)"
  "$VENV/bin/python" -c "import gunicorn, flask, spacy, torch, transformers, sentence_transformers, en_core_web_sm" \
    2>/dev/null || fail "$VENV is missing packages (set COMPOSE_VENV; requirements.txt + requirements-compose.txt)"
  [ -f "$REPO/models/enron_register_distilbert/model.safetensors" ] || fail "tone weights missing under $REPO/models"
  [ -d "$HOME/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base" ] || fail "NLI model not cached"
  (cd "$REPO" && "$VENV/bin/python" -c "from Src.source.pipeline import compose_prompt as cp; \
assert cp.fingerprint() == '$PROMPT_FINGERPRINT', cp.fingerprint()") || fail "prompt is not the one run 2 was trained on"
  grep -q PIPELINE_SERVICE_TOKEN "$REPO/Src/source/pipeline/service.py" \
    || fail "the code in $REPO has no token check - start it from a checkout that has it"

  stop >/dev/null      # our own agents, from an earlier start
  for p in $LLM_PORT $PORT; do
    # launchd returns before a stopped process has let go of its port.
    for _ in $(seq 1 20); do lsof -nP -iTCP:$p -sTCP:LISTEN -t >/dev/null 2>&1 || break; sleep 1; done
    pid=$(lsof -nP -iTCP:$p -sTCP:LISTEN -t 2>/dev/null | head -1 || true)
    [ -z "$pid" ] || fail "port $p is taken by pid $pid ($(ps -o command= -p "$pid" | cut -c1-90)) - stop that first"
  done

  if [ ! -s "$TOKEN_FILE" ]; then
    (umask 077; openssl rand -hex 32 > "$TOKEN_FILE")
    echo "made a new token in $TOKEN_FILE"
  fi
  chmod 600 "$TOKEN_FILE"
  mkdir -p "$AGENTS" "$LOGS"

  cat > "$AGENTS/$LLM_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LLM_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-is</string>
    <string>$LLAMA</string><string>-m</string><string>$MODEL</string>
    <string>--jinja</string><string>--chat-template-kwargs</string><string>{"enable_thinking":false}</string>
    <string>--host</string><string>127.0.0.1</string><string>--port</string><string>$LLM_PORT</string>
    <string>-c</string><string>16384</string><string>-ngl</string><string>99</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$LOGS/compose-llm.log</string>
  <key>StandardErrorPath</key><string>$LOGS/compose-llm.log</string>
</dict>
</plist>
EOF

  # The token is read when the service starts, so it never sits in the plist.
  cat > "$AGENTS/$SVC_LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$SVC_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-c</string>
    <string>export PIPELINE_SERVICE_TOKEN="\$(cat '$TOKEN_FILE')"; exec '$VENV/bin/gunicorn' --workers 1 --threads 4 --timeout 120 --bind 127.0.0.1:$PORT 'Src.source.pipeline.service:create_service()'</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>COMPOSE_LLM_URL</key><string>http://127.0.0.1:$LLM_PORT</string>
    <key>COMPOSE_MODEL_NAME</key><string>qwen3.5-4b-ft-run2</string>
    <key>HF_HUB_OFFLINE</key><string>1</string>
    <key>TRANSFORMERS_OFFLINE</key><string>1</string>
    <key>OBJC_DISABLE_INITIALIZE_FORK_SAFETY</key><string>YES</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$LOGS/compose-service.log</string>
  <key>StandardErrorPath</key><string>$LOGS/compose-service.log</string>
</dict>
</plist>
EOF

  launchctl bootstrap "$DOMAIN" "$AGENTS/$LLM_LABEL.plist"
  launchctl bootstrap "$DOMAIN" "$AGENTS/$SVC_LABEL.plist"

  echo "waiting for the model and the service to load..."
  for _ in $(seq 1 90); do curl -s -m 2 "127.0.0.1:$PORT/health" | grep -q '"enabled":true' && break; sleep 2; done
  curl -s "127.0.0.1:$PORT/health"; echo
  begin=$(date +%s)
  reply=$(curl -s -m 100 -X POST "127.0.0.1:$PORT/compose" -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
    -H 'Content-Type: application/json' -d '{"message":"could you send me the Q3 report by Friday?"}')
  echo "test rewrite in $(( $(date +%s) - begin ))s: $(echo "$reply" | grep -o '"degraded":[a-z]*')"
  echo "unauthenticated: HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST "127.0.0.1:$PORT/compose" \
    -H 'Content-Type: application/json' -d '{"message":"x"}') (should be 401)"
  echo "listening on 127.0.0.1:$PORT - publish it with Tailscale Funnel (README.md)"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: bash $0 start|status|stop"; exit 2 ;;
esac
