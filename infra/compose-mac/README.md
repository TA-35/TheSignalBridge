# Compose served from a Mac, published with Tailscale Funnel

A stopgap until the uni GPU server has an HTTPS route (`infra/compose-uni/`). Same service, same
token check, same remote mode on AWS - only the address changes, so moving to the uni server later
is two settings.

```
browser -> api.thesignalbridge.com (backend) -> AWS inference box :8100 (remote mode)
        -> https://<mac>.<tailnet>.ts.net  (Tailscale Funnel; TLS ends on the Mac)
        -> compose-service 127.0.0.1:8101 -> llama-server 127.0.0.1:8080 (run 2 on Metal)
```

When the Mac is off, asleep or offline, the AWS box answers Compose "degraded"
(`model_unavailable`), the same as before the cutover. Decode and the rest of the site are unaffected.

## 1. Start the services

```
COMPOSE_MODEL=<path to run 2's GGUF> COMPOSE_VENV=<venv with requirements.txt + requirements-compose.txt> \
  bash infra/compose-mac/mac_compose.sh start
```

It checks the model (sha256 34bd38e5...), the packages, the tone weights, the cached NLI model and
the prompt fingerprint, makes the token in `~/.compose_token` on first start, installs two launchd
agents and runs one rewrite. The agents start at login and restart if they stop; `caffeinate` keeps
the Mac awake while the model runs. `status` and `stop` do what they say. Logs are in
`~/Library/Logs/signalbridge/` and hold timings, never message text.

Keep the Mac plugged in, lid open and online, with the **uni VPN off**: public traffic must not go
through the uni network. The VPN is only needed to SSH into the GPU server.

## 2. Publish it with Tailscale Funnel

Use the open-source `tailscaled` from Homebrew - Tailscale's macOS comparison lists it as the variant
that supports Funnel (the App Store and Standalone apps are listed without it).

```
brew install tailscale
sudo brew services start tailscale
sudo tailscale up                    # log in with the link it prints
```

In the Tailscale admin console, DNS page: turn on MagicDNS and HTTPS Certificates. Then:

```
sudo tailscale funnel --bg 8101      # the first time, approve Funnel with the link it prints
sudo tailscale funnel status         # shows https://<mac>.<tailnet>.ts.net
```

`--bg` keeps it on across reboots until it is turned off. Check it from another network (a phone
hotspot): `curl https://<mac>.<tailnet>.ts.net/health` shows `"token_required": true`, and a POST
to `/compose` without the token answers 401.

## 3. Cut over the AWS inference box

Needs `main` with the token change (branch `deploy/compose-remote-auth`) deployed with the
inference-deploy workflow (`with_compose` false). Then on the box, as in
`infra/compose-uni/README.md` step 3: `cp ~/inference/.env ~/inference/.env.before-mac`, remove any
older `COMPOSE_REMOTE_*` lines and set

```
COMPOSE_REMOTE_URL=https://<mac>.<tailnet>.ts.net
COMPOSE_REMOTE_TOKEN=<the Mac's ~/.compose_token - copy it with: pbcopy < ~/.compose_token>
COMPOSE_REMOTE_TIMEOUT=25
COMPOSE_MODEL_NAME=qwen3.5-4b-ft-run2
```

then `sudo systemctl restart inference`. Check: `curl -s 127.0.0.1:8100/health` shows
`"remote": true`, and a rewrite on the live site comes back with `"degraded": false`.

**Rollback:** `cp ~/inference/.env.before-mac ~/inference/.env && sudo systemctl restart inference`.

## Stop, or move to the uni server

```
bash infra/compose-mac/mac_compose.sh stop
sudo tailscale funnel --https=443 off
```

Once the uni route exists, follow `infra/compose-uni/README.md`. Its token is a different one, so
update both `COMPOSE_REMOTE_URL` and `COMPOSE_REMOTE_TOKEN` on the AWS box, then stop the Mac.

## Secrets

The token lives only in `~/.compose_token` on the Mac (mode 600) and `~/inference/.env` on AWS.
The service agent reads it when it starts, so it never sits in a plist. Never commit it or paste it
into a ticket. To rotate: delete `~/.compose_token`, run `start` again, update the AWS `.env`,
restart `inference`.
