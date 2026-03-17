# CivicSpark AI

Civic engagement platform for Tulsa residents. AI-powered tools for city government interaction, meeting notifications, and community organizing.

**Archived.** This repository is the initial proof-of-concept. The project continues in active development with a new architecture. The demo was built in consultation with the Tulsa City Auditor's Office and local community organizations.

**Live demo:** [https://d1s9nkkr0t3pmn.cloudfront.net](https://d1s9nkkr0t3pmn.cloudfront.net)

![](homepage.png)

---

## Features

- **AI Chatbot** — RAG-enhanced responses using city budgets, legislation, and policies
- **Meeting Notifications** — Topic-based subscriptions (housing, transportation, etc.) via SMS and email
- **Meeting Analytics** — AI categorization of 42+ civic topics, searchable minutes
- **Representative Lookup** — District-based lookup with AI-powered email generation
- **Campaigns** — Campaign tracking and neighborhood organizing tools

---

## RAG System

The chatbot uses Retrieval-Augmented Generation (RAG) to search and cite actual city documents instead of generic responses.

**Pipeline:** Document upload → Text extraction → Chunking (512 tokens, 50 overlap) → Embeddings (OpenAI text-embedding-3-small) → Vector store (ChromaDB / FAISS) → Semantic search → Context injection at query time

**Components:** ChromaDB (dev) / FAISS (prod), PostgreSQL for metadata, FastAPI for upload/search

**Document types:** Budgets, legislation, meeting minutes, reports, policies

**Setup:** `pip install -r backend/requirements.txt` then `cd backend && python -m alembic upgrade head`. See [docs/RAG_SYSTEM_README.md](docs/RAG_SYSTEM_README.md).

---

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript, Vite, Tailwind |
| Backend | FastAPI, Python 3.11 |
| Database | PostgreSQL, Redis |
| AI | OpenAI GPT-4, RAG (ChromaDB/FAISS) |
| Infrastructure | AWS (ECS, RDS, S3, CloudFront) |

```
CloudFront → React SPA (S3) + FastAPI (ECS)
                    │
                    ├── PostgreSQL (RDS)
                    ├── Redis (ElastiCache)
                    ├── OpenAI API
                    └── RAG Vector Store (ChromaDB/FAISS)
```

---

## Project Structure

```
backend/          # FastAPI app
  app/api/v1/     # REST endpoints
  app/models/     # SQLAlchemy models
  app/services/   # Chatbot, vector, document processing
  app/scrapers/   # Tulsa city council data

frontend/         # React + TypeScript
  src/pages/      # Route components
  src/components/ # Shared UI

aws/              # Terraform, deployment scripts
docs/             # Documentation
tests/            # Backend (pytest), frontend (Jest)
```

---

## Quick Start

```bash
git clone https://github.com/kaizengrowth/CivicSpark_AI.git
cd CivicSpark_AI

# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp env.example .env
python -m app.main

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

- Frontend: http://localhost:3007
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

**Required env vars:** `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `SECRET_KEY`

---

## Documentation

| Document | Description |
|----------|-------------|
| [RAG System](docs/RAG_SYSTEM_README.md) | Document processing and vector search |
| [Vercel Deployment](docs/VERCEL_DEPLOYMENT.md) | Deploy on Vercel + Render free tier |
| [AWS Deployment](docs/aws-deployment-guide.md) | Production infrastructure |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues |

---

## License

MIT. See [LICENSE](LICENSE).

**Contact:** kaitlin.cort@owasp.org | [@kaizengrowth](https://github.com/kaizengrowth)
