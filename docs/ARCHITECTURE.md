# CivicSpark AI — Architecture

Design reference: [kaizencode.art/garden/citycamp-ai](https://kaizencode.art/garden/citycamp-ai/)
— the product sketch this architecture implements incrementally. The core
principle from that sketch: **structure the corpus, measure failure, then add
model cleverness — not the reverse.** Chat is one interface over an evidence
layer; the explorer, search, and watch digests must stay correct even if the
LLM is offline.

## Runtime shape

```
Vercel (React SPA, free tier)
  └─ /api/* rewrite ──► Render Web Service (FastAPI, Docker)
                          └─ Render Postgres  ◄── the ONLY stateful service
                               ├─ relational data (users, meetings,
                               │   campaigns, subscriptions, documents)
                               ├─ RAG vectors: document_chunks.embedding
                               │   (pgvector; JSON + numpy cosine fallback)
                               └─ FTS index (keyword half of hybrid search)

External APIs (all optional; features degrade gracefully):
  LLM chat        — any OpenAI-compatible endpoint; default Llama 3.3 70B on Groq (free)
  Embeddings      — any OpenAI-compatible endpoint; default Jina v3 (free tier)
  Twilio SMS · SMTP email · Geocod.io · Google CSE
```

No Redis, no Celery, no S3 (local-disk storage by default), no separate
vector database. Monthly infrastructure cost at small scale: $0.

### Why Postgres for vectors

The proof-of-concept wrote its Chroma/FAISS index to local disk — ephemeral
on every container platform, so each deploy silently wiped the RAG index.
Postgres already stores every chunk; keeping the embedding on the chunk row
makes the index exactly as durable as the data, with one backup story. At
civic-corpus scale (thousands of chunks, not millions) pgvector with an HNSW
index is more than sufficient, and the in-process numpy fallback keeps every
environment (SQLite tests, Postgres without the extension) working.

### LLM provider strategy

All chat and embedding traffic goes through OpenAI-compatible endpoints
(`app/core/llm.py`), configured by env var:

| Setting | Default |
|---|---|
| `LLM_BASE_URL` / `LLM_MODEL` | Groq / `llama-3.3-70b-versatile` |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | Jina / `jina-embeddings-v3` / 1024 |
| `OPENAI_API_KEY` | legacy fallback provider |

Swapping to OpenRouter, Together, or a local Ollama is configuration, not
code. Changing the embedding model/dimensions requires re-embedding the
corpus (the pgvector column is sized from config on fresh databases).

## Evidence layer (Iteration 1)

- **Provenance**: every document records `content_hash` (sha256) and
  `retrieved_at`; identical re-uploads are deduplicated;
  `/api/v1/documents/stats` reports `index_as_of`.
- **Hybrid retrieval**: dense (pgvector or numpy) ∪ keyword (Postgres FTS
  with GIN index; ILIKE fallback elsewhere), fused with reciprocal-rank
  fusion. Keyword search alone works with zero LLM keys — search before chat.
- **Legislative identity, not chunk soup**: agendas and minutes are parsed
  into their agenda tree (`app/services/agenda_parser.py`) and chunked per
  item; every chunk carries `meeting_id` / `agenda_item_id` / `item_number`,
  and those keys flow through search-result metadata. Unstructured documents
  fall back to fixed windows.
- **Deep links**: `GET /api/v1/meetings/{id}/items[/{item_id}]` is the
  canonical item record (structured fields + linked excerpts), and the
  meeting explorer keeps the selected meeting in the URL (`?meeting=<id>`),
  so citations and alerts land on the item, not the homepage.
- **Citations**: chat document excerpts carry source title, link, retrieval
  date, and a meeting-record deep link when identity is known. The system
  prompt forbids inventing figures, votes, or ordinance text: search and
  cite, or say the corpus lacks the answer.
- **Human-gated outreach**: representative emails are drafted and returned
  for review; the platform never sends on a user's behalf.
- **Eval seed**: `tests/backend/test_retrieval_eval.py` runs a frozen gold
  set (deterministic embeddings, no network) in CI — recall assertions fail
  the build when retrieval regresses. The real gold set, co-written with
  journalists and organizers, extends this corpus without changing the
  harness.

## Grounded Q&A (Iteration 2)

- **Intent routing** (`app/services/intent_router.py`): deterministic
  best-match classification (budget_fact, meeting_outcome, contact_rep,
  subscribe_topic, process_how_to) steers each query to the right evidence
  before any model call.
- **Numbers from table cells**: the `budget_lines` table (admin CSV import,
  `/api/v1/budget/*`) is the only source the chatbot may cite dollar figures
  from, via the `lookup_budget_line` tool — every row keeps its source
  document/page. No matching row → the tool says "do not guess" and links
  the official budget documents.
- **Multi-tool agent loop**: tool results (document search, budget lookup,
  `get_agenda_item`, `search_meetings`) are fed back to the model, which
  synthesizes a cited answer — no more raw tool dumps as responses.
- **Claim verification** (`ENABLE_CLAIM_VERIFICATION`, on by default): a
  second, temperature-0 pass checks the draft against the gathered evidence
  and removes or hedges unsupported claims; if the core answer is
  unsupported, it refuses and points to official sources. Fails open on
  errors.
- **Contested-issue policy** (in the system prompt): no soft-pedaling or
  evasion on housing, policing, budgets, or accountability — present what
  Council actually did (cited) as distinct from claims about it, surface
  staff reports and public comment where indexed, and disclose one-sided
  corpus coverage. The platform serves residents' right to know, not the
  city's narrative.

## Watches & feedback (Iteration 3)

- **Ingest-time matching** (`app/services/watch_service.py`): the moment a
  new meeting is upserted, active confirmed subscriptions are matched
  dual-track — item-level keyword hits outrank topic-label hits, which
  outrank bare meeting-type interest — and notifications are queued per
  channel with dedup. Matching never blocks ingestion.
- **Deep link first**: every alert leads with the meeting deep link
  (`/meetings?meeting=<id>`); matched item titles next; the AI summary is
  optional extra, never the only content.
- **Consent**: one-click unsubscribe via HMAC-signed expiring tokens
  (`app/core/tokens.py`, `GET /subscriptions/unsubscribe?token=...`) in
  every message — no login, no enumerable IDs. Quiet hours, digest mode,
  and per-day caps live on the subscription and are honored at dispatch.
  Zero auto-sends anywhere in the platform.
- **Feedback review queue** (`chat_feedback`, `POST /chatbot/feedback`):
  every thumbs-down is a work item tagged with its routed intent; the
  admin queue (`GET /chatbot/feedback?reviewed=false`) is the product
  backlog — each miss becomes a corpus, prompt, or tool fix.

## Matters graph (Iteration 4)

- **Longitudinal tracking** (`app/services/matter_service.py`): official
  identifiers — zoning applications (Z-7642), PUDs, BOA cases, ordinance
  and resolution numbers — are extracted from agenda items at ingest and
  resolved to a persistent `Matter`. Each sighting becomes a
  `MatterAppearance` with the inferred action (introduced / discussed /
  amended / postponed / vote_passed / vote_failed), the recorded vote
  result, and the evidence span it came from.
- **Status from the record**: a matter's status derives from its latest
  appearance; terminal outcomes (passed/failed) are never downgraded by
  backfilling older meetings. The graph asserts only what the record shows.
- **Surfaces**: `GET /api/v1/matters` (list/search), `/matters/{id}` and
  `/matters/by-key/{key}` (timeline with per-meeting deep links), and the
  chatbot's `track_matter` tool — "where is Z-7642 in the process?" is
  answered from the graph, with a refusal when the matter isn't tracked.
- **Transcript/video sync**: meeting videos are transcribed for free on
  GitHub Actions (`.github/workflows/transcribe.yml` → faster-whisper on
  CPU; a ~3h meeting fits well inside the 6h job limit at $0). Timestamped
  segments land in `transcript_segments` via a shared-secret machine-ingest
  endpoint (`POST /meetings/{id}/transcript`, `TRANSCRIPT_INGEST_TOKEN`),
  and `GET /meetings/{id}/transcript?q=` returns every quote with a
  `video_link` pointing at its exact moment in the recording.
- **Deliberately out (for now)**: councilor stance summaries — per the
  design sketch those ship only with evidence spans and confidence labels,
  never as unlabeled fact.

## Schema setup

Fresh databases bootstrap via `create_tables()` (SQLAlchemy `create_all`) at
startup, then `ensure_pgvector()` idempotently enables the extension, adds
the `embedding` column, backfills from JSON, and creates the HNSW + FTS
indexes. Alembic migrations 005–007 mirror the same steps for
migration-managed databases. (The pre-005 chain assumes tables that
`create_all` historically made, so it is not runnable from scratch — a known
limitation inherited from the PoC.)

## Roadmap (from the design sketch)

| Iteration | Scope | Status |
|---|---|---|
| 1 — Evidence layer | provenance, hybrid index, item-level parsing, deep links | **shipped** on this branch (vendor-adapter hardening for TGOV/Granicus feeds remains ongoing) |
| 2 — Grounded Q&A | intent routing, rerank, claim verification, budget tools, gold eval set | **largely shipped**: intent router, budget tools, agent loop, claim verification, contested-issue policy, eval harness seed. Remaining: cross-encoder rerank, gold set expansion from research-day transcripts |
| 3 — Watches & outreach | ingest-time watch matching, deep-link-first alerts, consent hardening | **largely shipped**: dual-track matching at ingest, deep-link-first messages, signed one-click unsubscribe, feedback review queue. Remaining: digest dispatch loop, alert-retention metrics |
| 4 — Matters graph | track legislative matters across meetings; optional media | **shipped**: identifier extraction, cross-meeting timelines, status inference, API + track_matter tool, free Actions-based transcript/video sync. Remaining: evidence-labeled stance summaries, transcript↔agenda-item alignment |

The failure modes in the design sketch are the acceptance tests: if budget
questions are still answered from chunk soup without citations, it isn't an
improvement — it's a prettier PoC.

## Local development

```bash
docker compose up          # pgvector Postgres + API + frontend
# or natively:
cd backend && pip install -r requirements-dev.txt && python -m app.main
cd frontend && npm install && npm run dev
```

## Deployment

- **Render**: connect the repo as a Blueprint (`render.yaml`) — one web
  service + one Postgres. Set `LLM_API_KEY` (Groq) and `EMBEDDING_API_KEY`
  (Jina) in the dashboard.
- **Vercel**: import the repo (`vercel.json`) — static build of `frontend/`,
  `/api/*` proxied to the Render service, so no CORS configuration is needed.
