# Read_the_room_iteration_1

A local-first web app that separates what a workplace message *actually says* from what it *leaves unsaid*, and turns each decode into a reusable, judgement-free lesson in workplace communication.

> Access our website: https://reedtheroom.online/




## Repository layout

```
frontend/   Vue 3 + Vite PWA
backend/    Flask app, migrations, tests
infra/      nginx conf, systemd unit version-controlled, not just on the box
docs/       api-contract.md
```

See [docs/api-contract.md](docs/api-contract.md) for the frontend/backend/AI API contract.

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

![](docs/pics/system%20architectural%20design.png)
