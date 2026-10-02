# TheSignalBridge

A local-first web app that separates what a workplace message *actually says* from what it *leaves unsaid*, and turns each decode into a reusable, judgement-free lesson in workplace communication.

> Access our website: https://www.thesignalbridge.com/




## Repository layout

```
frontend/   Vue 3 + Vite PWA
backend/    Flask app, migrations, tests
infra/      nginx conf, systemd unit version-controlled, not just on the box
docs/       api-contract.md
```

See [docs/api-contract.md](docs/api-contract.md) for the frontend/backend/AI API contract.

### Shared website password

The website sits behind one shared password, enforced by the CloudFront function in [infra/cloudfront/basic-auth.js](infra/cloudfront/basic-auth.js).

It has to be enforced at CloudFront, not in Nginx. The frontend is a private S3 bucket served through CloudFront distribution `E1YGUMFRDSPNVG`, and both `thesignalbridge.com` and `www.thesignalbridge.com` resolve there. The EC2 box under [infra/nginx/](infra/nginx/) only serves `api.thesignalbridge.com`, so an `auth_basic` block there never sees website traffic.

This covers the website only. `api.thesignalbridge.com` stays public, because the browser calls it cross-origin and would not attach the password to those requests.

**The password is never committed.** `basic-auth.js` carries a `__BASIC_AUTH_TOKEN__` placeholder; `infra/cloudfront/publish.sh` substitutes the real value from the environment into a copy outside the working tree, so the checked-in file and the deployed function differ on purpose. Ask a teammate for the current password rather than looking for it in the repo.

To set or rotate it, run from the repo root:

```sh
SITE_AUTH_USER=thesignalbridge SITE_AUTH_PASSWORD='<the password>' \
  ./infra/cloudfront/publish.sh
```

That uploads the function, verifies it returns a 401 challenge before going live, publishes it, and attaches it to the distribution if it isn't attached yet. Rotating is the same command with a new value — no code edit. Edges take a few minutes to catch up; confirm with:

```sh
curl -sI https://www.thesignalbridge.com/ | head -3    # expect HTTP/2 401
```

## Local development

### Frontend

```
cd frontend
npm install
npm run dev
```

### Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env     # then fill in DATABASE_URL etc.
flask --app wsgi run
```

Run backend tests with `pytest` from `backend/`.


### Database

Needs a local PostgreSQL instance matching the `DATABASE_URL` in `backend/.env`. Easiest via Docker:

```
docker run --name readtheroom-db -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -e POSTGRES_DB=readtheroom -p 5432:5432 -d postgres:16
```

With the backend venv active and `.env` pointing at that database:

```
cd backend
flask --app wsgi db upgrade         # create the schema
python scripts/seed_patterns.py     # load the pattern library
```

`seed_patterns.py` reads from `data/library_dataset/library_dataset.json`

## Architecture Diagram

![](docs/pics/System%20architecture%20diagram.png)
