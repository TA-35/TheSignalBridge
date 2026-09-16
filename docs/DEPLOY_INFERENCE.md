# Deploying the inference service

The LLM review pipeline runs as its own service, separate from the API. This
is the runbook for standing it up.

**Nothing in production changes until the last step.** Steps 1–3 provision a
service nobody is calling; step 4 switches it on. If you stop after step 3,
the site behaves exactly as it does today.

## Why it is separate

Measured: the pipeline holds **~505 MB resident** once spaCy, scikit-learn and
both model bundles load. The API box is a t3.micro (1024 MB) running three
gunicorn workers — importing it there would need ~1435 MB and would not fit.
Dropping the API to one worker to make room would put every 50 ms
`/api/decode` behind a 9-second model call.

So it gets its own host, and the API reaches it over HTTP.

## Prerequisites

- AWS access to create an EC2 instance
- Ability to add a GitHub Actions secret to this repo
- An LLM API key (NVIDIA NIM `nvapi-…`, or Moonshot `sk-…`)
- SSH access to the existing API box for step 4

---

## Step 1 — Provision the inference host

**Size it for ~505 MB plus the OS.** A `t3.small` (2 GB) is comfortable;
`t3.micro` (1 GB) will work but leaves little headroom. Same VPC and region as
the API box (`ap-southeast-2`), so the API can reach it privately.

Security group, two rules:

- **22/tcp inbound** — so GitHub Actions can deploy. The runners have no fixed
  IP range worth allowlisting, so this matches how the API box is already
  reached.
- **8100/tcp inbound from the API box's security group only** — never
  `0.0.0.0/0`. The service has **no authentication**; anything that can reach
  port 8100 can spend your model credits.

On the new host:

```sh
sudo apt update && sudo apt install -y python3-venv python3-pip rsync
mkdir -p ~/inference
```

Add the CI deploy key's **public** half to `~/.ssh/authorized_keys` — the same
key the backend deploy uses, stored as the `EC2_SSH_PRIVATE_KEY` secret.

### Create the environment file

This is **mandatory**. Without it the service starts, reports
`has_credentials: false`, and defaults to the wrong provider — verified.

```sh
cat > ~/inference/.env <<'EOF'
NVIDIA_API_KEY=nvapi-your-real-key
PIPELINE_LLM_PROVIDER=nvidia
PIPELINE_LLM_MODEL=meta/llama-3.2-11b-vision-instruct
PIPELINE_LLM_MAX_TOKENS=4000
PIPELINE_LLM_TIMEOUT=900
EOF
chmod 600 ~/inference/.env
```

Using Moonshot directly instead? `MOONSHOT_API_KEY=sk-…` and
`PIPELINE_LLM_PROVIDER=openai`. Sending one provider's key to the other's
endpoint fails as `AuthenticationError`, which reads like a bad key but is a
wrong address — the prefix tells you which you have.

### Install the service unit

```sh
scp infra/systemd/inference.service ubuntu@<inference-host>:/tmp/ && \
  ssh ubuntu@<inference-host> "sudo mv /tmp/inference.service /etc/systemd/system/"
sudo systemctl daemon-reload
sudo systemctl enable inference
```

Don't start it yet — there is no code on the host until step 3.

---

## Step 2 — Add the GitHub secret

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `INFERENCE_HOST` | the instance's **public** DNS name or public IP |

**Public, not private.** GitHub Actions runners live on GitHub's
infrastructure, outside your VPC, so they can only SSH to an address reachable
from the internet. The existing `EC2_SSH_PRIVATE_KEY` secret is reused and no
other secret is needed.

This is the opposite of `INFERENCE_URL` in step 4, and mixing them up is the
easiest mistake here:

| Setting | Used by | Address | Reason |
|---|---|---|---|
| `INFERENCE_HOST` | GitHub Actions, at deploy time | **public** | the runner is outside the VPC |
| `INFERENCE_URL` | the API box, at request time | **private** | keeps model traffic off the internet |

Prefer the public **DNS name** over the public IP: a stopped and restarted
instance gets a new public IP unless you attach an Elastic IP, and the secret
would then be stale with no obvious symptom beyond the deploy failing to
connect.

---

## Step 3 — First deploy

Actions → **Inference service deploy** → Run workflow.

It runs the pipeline's 210 tests, checks the API's dependency list has not
grown, rsyncs `Src/`, `models/` and the one backend module the extractor comes
from, builds a virtualenv, and restarts the unit.

Verify on the host:

```sh
curl -s http://127.0.0.1:8100/health
```

Expected:

```json
{"status":"ok","provider":"nvidia",
 "model":"meta/llama-3.2-11b-vision-instruct",
 "has_credentials":true,"max_message_chars":5000}
```

**`has_credentials: false` means `.env` is missing or unreadable by the
`ubuntu` user.** Fix that before continuing — the service will start anyway
and every review will degrade.

Then check a real call end to end:

```sh
curl -s -X POST http://127.0.0.1:8100/analyse \
  -H 'Content-Type: application/json' \
  -d '{"message":"Could you send the report to the client by Friday?"}'
```

Should return in milliseconds with `deadline` and `required_action` spans.

---

## Step 4 — Switch it on (the only step users can see)

**Do this last, and only once step 3's health check passes.**

Measured behaviour when `INFERENCE_URL` is wrong:

| State | Response time |
|---|---|
| Unset (the rollback state) | **0.5 ms** |
| Set, connection refused (nothing listening) | **9 ms** |
| Set, packets dropped (security group `DROP`, or a hung service) | **the full timeout — 30 s** |

A refused connection fails fast, so a simply-absent service is not the
disaster. The one that hurts is a host that accepts the SYN and never
answers: a security group that drops rather than rejects, or a service that
is up but wedged. Every review then waits 30 seconds before degrading.

So: finish step 3 and see a green health check before doing this. And if
reviews suddenly get slow, suspect this first.

On the **API** box, using the inference instance's **private** IP (the
`10.x.x.x` or `172.31.x.x` address, not the public one from step 2):

```sh
# find it from the API box - the private address is what stays inside the VPC
echo 'INFERENCE_URL=http://10.0.1.23:8100' >> ~/app/.env   # your private IP
sudo systemctl restart backend
```

Using the public address here would route every review out to the internet and
back, adding latency and exposing traffic that has no reason to leave the VPC.

Verify from anywhere:

```sh
curl -s https://api.thesignalbridge.com/api/review/health
```

`{"reachable": true, "inference": {...}}` means both services are up and can
see each other.

---

## Telling the two services apart when something breaks

| Symptom | Meaning |
|---|---|
| `/api/patterns` fails | The **API** is down. Nothing to do with this service. |
| `/api/patterns` fine, `/api/review/health` says `reachable: false` | The **inference service** is down or unreachable. The site still works; reviews degrade. |
| `reachable: true`, but reviews return `degraded: true` | The service is up but the **model** call is failing — check `has_credentials`, the key's quota, and `journalctl -u inference`. |
| Reviews are slow but succeed | Normal. 5–9 s is the model, not a fault. |

Logs: `sudo journalctl -u inference -f`

---

## Rolling back

Removing `INFERENCE_URL` from the API's `.env` and restarting the backend
returns the site to exactly its pre-integration behaviour. `/api/review` goes
back to degrading instantly, `/api/decode` was never touched, and the
inference host can be left running or stopped without affecting anything.

```sh
sed -i '/^INFERENCE_URL=/d' ~/app/.env
sudo systemctl restart backend
```

That is the whole rollback. No database change, no migration, no frontend
deploy is involved.

---

## What is deliberately not automated

- **Provisioning.** One-off, and it needs AWS credentials CI does not have.
- **Setting `INFERENCE_URL`.** It is the switch that makes the feature live,
  and it should be a deliberate act by someone watching the result.
- **The frontend.** `reviewService.ts` and `types/review.ts` are committed and
  type-check, but no component calls them yet. Until one does, `/api/review`
  has no user-facing effect regardless of this deployment.
