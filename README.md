# Read_the_room_iteration_1

A local-first web app that separates what a workplace message *actually says* from what it *leaves unsaid*, and turns each decode into a reusable, judgement-free lesson in workplace communication.

See [docs/api-contract.md](docs/api-contract.md) for the frontend/backend/AI API contract.

## Repository layout

```
frontend/   Vue 3 + Vite PWA
backend/    Flask app, migrations, tests
infra/      nginx conf, systemd unit version-controlled, not just on the box
docs/       api-contract.md
```

`ai-service/` is not yet part of the layout (TODO), waiting for the "hosted-vs-self-hosted" model decision  

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

## Architecture

Public content (the curated `patterns` table) comes down from the API; user data(pasted messages), saved flashcards, review history will never goes up. No accounts, no server-side user data.
