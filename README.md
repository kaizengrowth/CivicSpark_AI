# CivicSpark AI

Civic engagement platform for Tulsa residents: a searchable evidence layer
over city government documents, with AI assistance on top — meeting explorer,
grounded Q&A, topic notifications, representative lookup, and organizing
tools.

Built in consultation with the Tulsa City Auditor's Office and local
community organizations. Design notes and iteration plan:
[kaizencode.art/garden/citycamp-ai](https://kaizencode.art/garden/citycamp-ai/)

![](homepage.png)

---

## Features

- **Meeting Explorer** — searchable agendas and minutes, AI categorization
  across 42+ civic topics
- **Grounded Q&A** — chatbot answers cite actual city documents (budgets,
  legislation, policies) with source links and retrieval dates; it refuses
  rather than invents figures
- **Topic Watch** — subscriptions (housing, transportation, …) via SMS and
  email
- **Representative Lookup** — district lookup by address, with AI-drafted
  constituent email that the user reviews and sends themself — never
  auto-sent
- **Campaigns** — campaign tracking and neighborhood organizing tools

---

## Architecture

One database, one API, one static frontend. Runs free at small scale.

```
Vercel (React SPA) ─ /api/* ─► Render (FastAPI) ─► Postgres (pgvector)
                                                     ├─ relational data
                                                     ├─ RAG vector index
                                                     └─ full-text search
```

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript, Vite, Tailwind (Vercel) |
| Backend | FastAPI, Python 3.11 (Render, Docker) |
| Database | PostgreSQL + pgvector — the only stateful service |
| LLM | Open-source models via any OpenAI-compatible API — Llama 3.3 70B on Groq by default |
| Embeddings | Jina v3 by default (configurable; numpy fallback needs no extension) |

Key properties:

- **The index survives deploys** — vectors live on document chunks in
  Postgres, not on ephemeral disk
- **Search before chat** — hybrid retrieval (FTS ∪ dense vectors, rank
  fusion) works even with no LLM configured
- **Provenance everywhere** — every document records source hash and
  retrieval time; the API reports how fresh the index is
- **Provider-agnostic AI** — swap Groq for OpenRouter, Together, or local
  Ollama by env var; no OpenAI dependency

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
roadmap.

---

## Quick Start

```bash
git clone https://github.com/kaizengrowth/CivicSpark_AI.git
cd CivicSpark_AI

# Everything at once (pgvector Postgres + API + frontend):
docker compose up

# Or natively:
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp env.example .env   # add your LLM_API_KEY (Groq) + EMBEDDING_API_KEY (Jina)
python -m app.main

cd frontend && npm install && npm run dev
```

- Frontend: http://localhost:3007
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

**Required env vars:** `DATABASE_URL`, `SECRET_KEY`, `LLM_API_KEY`
(everything else is optional — features degrade gracefully).

---

## Deployment

| Target | How |
|--------|-----|
| Render (API + Postgres) | Connect the repo as a Blueprint — [render.yaml](render.yaml) |
| Vercel (frontend) | Import the repo — [vercel.json](vercel.json) proxies `/api/*` to Render |

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, evidence layer, roadmap |
| [Design sketch](https://kaizencode.art/garden/citycamp-ai/) | Product direction, peer systems, failure modes |

---

## License

MIT. See [LICENSE](LICENSE).

**Contact:** kaitlin.cort@owasp.org | [@kaizengrowth](https://github.com/kaizengrowth)
