# CivicSpark AI

An **evidence-first civic platform** for Tulsa, Oklahoma: searchable
council agendas and minutes with deep links to source documents,
grounded Q&A that cites (or refuses), ingest-time topic alerts, and
district lookup — retrieval and transparency before AI.

Built in consultation with the Tulsa City Auditor's Office and local
community organizations. Design notes and roadmap:
[kaizencode.art/garden/citycamp-ai](https://kaizencode.art/garden/citycamp-ai/).

![](homepage.png)

---

## Product surfaces

- **Meeting Explorer** — agendas and minutes from City of Tulsa
  sources, parsed to the agenda-item level. Every item has a shareable
  deep link (`/meetings/42#item-4.a`), topic labels from a fixed
  40-label civic taxonomy, resolved entities (councilors, districts,
  ordinance numbers), and a link to its exact source PDF pages.
- **Hybrid search** — `GET /api/v1/search`: Postgres FTS + pgvector
  dense retrieval fused with Reciprocal Rank Fusion; every result
  carries provenance (source URL, retrieval timestamp, content hash).
- **Grounded Q&A** — cite-then-verify pipeline: intent routing →
  hybrid retrieval → rerank → generation under a mandatory citation
  contract → claim verification (numeric figures must appear verbatim
  in the cited source) → refusal when evidence is missing. The system
  prompt contains zero hardcoded facts.
- **Topic Watch** — subscriptions matched at *ingest time* against new
  agenda items; alerts are deep-link-first (item + link, never an AI
  summary alone) via Resend email or Twilio SMS.
- **District lookup + outreach** — address → council district →
  representative, with human-gated email drafting (nothing auto-sends).

## Data sources

| Source | Used for |
|---|---|
| `tulsa-ok.granicus.com` (TGOV) | Meeting listings, agendas, minutes, video links |
| `cityoftulsa.org/apps/TulsaCouncilArchive` | Historical backfill (COTDisplayDocument PDFs) |

Ingestion runs nightly via GitHub Actions → `POST /api/v1/ingest/run`
(token-protected). Every run is recorded in `scrape_runs`; if the last
success is older than 7 days, `GET /api/v1/ingest/status` flips stale
and the UI shows a warning banner — scraper breakage is visible, never
silent. Some pre-2024 documents are missing from city systems
(ransomware incident); fetch failures are recorded per document.

```bash
cd backend
python -m app.cli ingest --source granicus --since 2025-01-01
python -m app.cli backfill-embeddings
python -m app.cli status
```

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript, Vite, Tailwind (Vercel) |
| Backend | FastAPI, Python 3.11 (Render) |
| Database | Supabase Postgres with pgvector + FTS (one datastore) |
| AI | OpenAI (gpt-4.1 answers, gpt-4.1-mini routing/rerank/verify, text-embedding-3-small) |

```
Vercel (React SPA) ── /api/* rewrite ──> Render (FastAPI)
                                            │
                                            ├── Supabase Postgres
                                            │     ├── pgvector HNSW (dense)
                                            │     ├── tsvector GIN (keyword)
                                            │     └── provenance + scrape_runs
                                            ├── OpenAI API
                                            └── Resend / Twilio (alerts)
GitHub Actions cron ──> POST /ingest/run (nightly Tulsa ingest)
```

## Evaluation

A frozen gold set (`tests/evals/gold_set.yaml`) is scored by
`python -m app.evals.runner` into `docs/evals/scorecard.md`: refusal
quality (adversarial budget bait must refuse), citation accuracy,
numeric accuracy, groundedness, and temporal correctness (superseded
documents must not be cited). Runs weekly via
`.github/workflows/eval.yml`; `pytest -m eval` enforces hard floors.

## Quick start

```bash
git clone https://github.com/kaizengrowth/CivicSpark_AI.git
cd CivicSpark_AI

docker compose up -d postgres      # pgvector/pgvector:pg16

# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp env.example .env                # add OPENAI_API_KEY etc.
alembic upgrade head
python -m app.cli ingest --source granicus --limit 10
python -m app.main

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

- Frontend: http://localhost:3000
- API: http://localhost:8000 (docs at /docs in debug mode)

**Required env vars:** `DATABASE_URL`, `SECRET_KEY`, `OPENAI_API_KEY`;
optional: `GEOCODIO_API_KEY`, `RESEND_API_KEY`, `TWILIO_*`,
`INGEST_API_TOKEN`. See `backend/env.example`.

## Project structure

```
backend/
  app/api/v1/       # REST endpoints (search, meetings, ingest, chatbot, ...)
  app/ingestion/    # Source adapters, structure-aware parsing, pipeline
  app/services/     # Hybrid search, QA (cite-then-verify), topic watch
  app/services/qa/  # intent / rerank / answer / verify / tools
  app/evals/        # Gold-set runner -> docs/evals/scorecard.md
  app/models/       # SQLAlchemy models
  alembic/          # Migrations (pgvector, provenance, taxonomy)
frontend/
  src/pages/        # MeetingsPage, MeetingDetailPage (deep links), ...
  src/components/   # ChatbotWidget (citations), StalenessBanner, ...
tests/
  backend/          # pytest (parsers, hybrid search, verification)
  evals/            # Frozen gold set + eval suite (pytest -m eval)
```

## Development

```bash
cd backend && ruff check app/ && ruff format app/ && mypy app/api app/services
cd frontend && npm run lint && npm run type-check && npm test
pytest tests/backend/
```

Pre-commit hooks (`pre-commit install`) run ruff, mypy, eslint,
bandit, and gitleaks.

## License

MIT. See [LICENSE](LICENSE).

**Contact:** kaitlin.cort@owasp.org | [@kaizengrowth](https://github.com/kaizengrowth)
