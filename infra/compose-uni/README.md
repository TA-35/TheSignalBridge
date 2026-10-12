# Compose on the uni GPU server, reached over HTTPS

```
browser -> api.thesignalbridge.com (backend) -> AWS inference box :8100 (remote mode)
        -> https://<uni host>  (eSolutions routing) -> uni compose-service :<port>
        -> llama-server 127.0.0.1:8080 (run 2 on the T4) + classifiers + grounding check
```

Until the cutover the live site answers Compose "degraded" (rewrite = null), and
Decode is unaffected. Every step below can be undone, and a broken step can only
degrade Compose: the AWS box answers `model_unavailable` when the uni service is
unreachable, refuses the token or times out.

## 1. Ready the uni server (VPN on)

1. Sync the code, `main` at or after the token change (rsync `Src/` and `models/`
   to `~/signalbridge`; the tone weights `models/enron_register_distilbert/model.safetensors`
   are Drive-only, copy them too).
2. The model: `runs/run2/merged_gguf/Qwen3.5-4B.Q4_K_M.gguf` is already on the box.
   Copy it to `~/models/compose/run2.Q4_K_M.gguf` (sha256 34bd38e5..., checked by the script).
3. Hugging Face is blocked there: copy the NLI model from a laptop's
   `~/.cache/huggingface/hub/models--cross-encoder--nli-deberta-v3-base`.
4. `bash infra/compose-uni/uni_compose.sh 8100` - localhost only. It checks
   everything above, installs `compose-llm` and `compose-service`, makes the token
   in `~/.compose_token` and runs one rewrite.

## 2. When eSolutions confirm the routing

Ask them for: the HTTPS URL, the port they forward to, and that TLS ends at their
proxy (the token travels in a header, so plain HTTP over the internet is not
acceptable). If they can, limit it to the AWS inference box's address, 13.238.174.232.

1. `bash infra/compose-uni/uni_compose.sh <their port> --public`
2. From a laptop: `curl https://<uni host>/health` answers with `"token_required": true`,
   and `curl -X POST https://<uni host>/compose/quick -d '{"message":"hi"}' -H 'Content-Type: application/json'`
   answers 401 without the token.

## 3. Cut over the AWS inference box

1. Deploy `main` with the inference-deploy workflow (`with_compose` false: in remote
   mode nothing heavy loads there). Harmless before step 2: no token is sent until
   one is set.
2. On the box: `cp ~/inference/.env ~/inference/.env.before-uni`, then set these in
   `~/inference/.env` (remove any older `COMPOSE_REMOTE_URL` line first):
   ```
   COMPOSE_REMOTE_URL=https://<uni host>
   COMPOSE_REMOTE_TOKEN=<contents of ~/.compose_token on the uni server>
   COMPOSE_REMOTE_TIMEOUT=25
   COMPOSE_MODEL_NAME=qwen3.5-4b-ft-run2
   ```
   `COMPOSE_REMOTE_TIMEOUT=25`, not the default 95: the API's gunicorn has three sync
   workers and the default 30s worker timeout (`infra/systemd/backend.service`), so a
   hung uni service must answer "degraded" here before the API's worker is killed -
   otherwise a few stuck rewrites would stall Decode too. A rewrite on the T4 takes
   a few seconds, about 15 with a retry.
3. `sudo systemctl restart inference` (Decode is out for the few seconds it takes to
   load; the API degrades, it doesn't fail).
4. Check: `curl -s 127.0.0.1:8100/health` shows `"remote": true`; then a rewrite on
   the live site, or `curl -X POST https://api.thesignalbridge.com/api/compose ...`,
   comes back with `"degraded": false`.

**Rollback:** `cp ~/inference/.env.before-uni ~/inference/.env && sudo systemctl restart inference`.
Compose is back to degraded, Decode as before. On the uni server,
`sudo systemctl disable --now compose-service compose-llm` stops serving.

## 4. Remove the abandoned tunnel pieces on AWS (optional, recommended)

The earlier SSH-tunnel attempt (`infra/compose-tunnel/`) left these on the inference
box; HTTPS doesn't need them. Do it from an EC2 Instance Connect session, so a
mistake in sshd can't lock you out:

```
sudo rm -f /etc/ssh/sshd_config.d/50-llm-tunnel.conf && sudo sshd -t && sudo systemctl reload sshd
id llmtunnel >/dev/null 2>&1 && sudo userdel -r llmtunnel
aws ec2 revoke-security-group-ingress --group-id sg-0f5d56359391b5281 --protocol tcp --port 443 --cidr 13.54.222.2/32
```

## Secrets

The token lives only in `~/.compose_token` on the uni server (mode 600) and
`~/inference/.env` on the AWS box. Never commit it or paste it into a ticket.
To rotate: delete `~/.compose_token`, rerun the script, update the AWS `.env`, restart.
