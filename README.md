# 🏛️ CivicSpark AI - Tulsa Civic Engagement Platform

> **📦 ARCHIVED DEMO REPOSITORY**: This repository represents our initial proof-of-concept, developed through extensive consultation and UI testing with community organizations and city government offices in Tulsa. After validating the platform's value and gathering critical user feedback, we are implementing a new version with cost-efficient infrastructure and a focused product roadmap. The CivicSpark AI project continues in active development.

---

A comprehensive CivicTech platform connecting Tulsa residents with city government through AI-powered tools, automated notifications, and intelligent meeting analytics.

## 📊 Project Status & Info

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tech Stack](https://img.shields.io/badge/stack-React%2BFastAPI%2BPostgreSQL-blue)](#-architecture)
[![GitHub last commit](https://img.shields.io/github/last-commit/kaizengrowth/CityCamp_AI)](https://github.com/kaizengrowth/CityCamp_AI/commits/main)
[![GitHub stars](https://img.shields.io/github/stars/kaizengrowth/CityCamp_AI)](https://github.com/kaizengrowth/CityCamp_AI/stargazers)

> **🌐 Deployed Demo**: [https://d1s9nkkr0t3pmn.cloudfront.net](https://d1s9nkkr0t3pmn.cloudfront.net)

## 📸 Platform Screenshots

![CivicSpark AI Homepage](homepage.png)

*CivicSpark AI homepage — AI-powered civic engagement platform connecting Tulsa residents with city government*

![CivicSpark AI Hero](frontend/src/assets/images/Hero.png)

*Platform hero section showing the core value proposition for Tulsa civic participation*

## 🌟 Features

### 🤖 **AI-Powered Civic Assistant**
- Interactive chatbot with real-time city council knowledge
- **RAG-Enhanced Responses**: Document-based answers using city budgets, legislation, and policies
- Natural language queries about Tulsa government with contextual document search
- Meeting summary generation and analysis

### 📅 **Smart Meeting Notifications**
- Automated alerts for city council meetings
- Topic-based subscriptions (housing, transportation, etc.)
- SMS and email delivery with AI-categorized content

### 📊 **Intelligent Meeting Analytics**
- AI categorization of 42+ civic topics
- Automated agenda extraction and impact assessment
- Searchable meeting minutes with keyword analysis

### 💬 **Representative Communication**
- AI-powered email generation to contact officials
- District-based representative lookup
- Pre-built templates for common civic issues

### 🗳️ **Community Engagement**
- Campaign tracking and petition management
- Neighborhood-based organizing tools
- User preference and notification management

---

## 📄 RAG Data Pipeline System (Retrieval-Augmented Generation)

The RAG system is the core AI intelligence layer that enables the chatbot to search and reference actual city documents, budgets, legislation, and policies — providing accurate, source-backed answers instead of generic responses.

### 🎯 What is RAG?

Traditional chatbots are limited to their training data. The RAG system extends the chatbot with a **live document retrieval layer**: when a resident asks a question, the system searches a vector database of real city documents and injects the most relevant passages into the AI prompt as grounded context. This produces responses that cite specific city ordinances, budget line items, or meeting minutes.

### 🔄 RAG Data Pipeline Overview

```
📄 Document Upload (PDF/DOCX/TXT)
        │
        ▼
🔤 Text Extraction
   (PyPDF2, python-docx, smart fallbacks)
        │
        ▼
✂️  Intelligent Chunking
   (Token-aware, 512-token chunks with 50-token overlap)
        │
        ▼
🧠 AI Enhancement
   (GPT-4 auto-generates summaries & keyword tags)
        │
        ▼
🔢 Embedding Generation
   (OpenAI text-embedding-3-small → 1536-dim vectors)
        │
        ├──────────────────────────────────────────┐
        ▼                                          ▼
💾 PostgreSQL Storage                   🗂️ Vector Database
   (Document metadata, chunks,              (ChromaDB in dev /
    processing status, audit log)            FAISS in production)
        │                                          │
        └──────────────┬───────────────────────────┘
                       │
               User Query arrives
                       │
                       ▼
🔍 Semantic Vector Search
   (Cosine similarity over embedded query)
                       │
                       ▼
📋 Top-K Chunk Retrieval
   (Relevance-scored passages from city docs)
                       │
                       ▼
🤖 Context-Augmented Prompt
   (Chunks injected into GPT-4 system prompt
    via OpenAI function calling)
                       │
                       ▼
✨ Grounded AI Response
   (Answer cites specific city documents)
```

### 🧩 RAG System Components

| Component | Technology | Role |
|-----------|-----------|------|
| **Vector Store (dev)** | ChromaDB | Local vector storage & similarity search |
| **Vector Store (prod)** | FAISS | High-performance production vector search |
| **Embeddings** | OpenAI `text-embedding-3-small` | 1536-dimensional vector representations |
| **Text Extraction** | PyPDF2, python-docx | Multi-format document parsing |
| **Chunking Engine** | Custom token-aware splitter | 512-token chunks, 50-token overlap |
| **AI Enhancement** | GPT-4 | Auto-summary and keyword generation |
| **Metadata Store** | PostgreSQL (RDS) | Document metadata, chunk tracking |
| **Search API** | FastAPI endpoints | Upload, search, manage documents |
| **Chatbot Integration** | OpenAI Function Calling | RAG retrieval triggered within conversations |

### 📁 Supported Document Types

| Type | Examples |
|------|---------|
| 💰 **Budgets** | City financial documents, departmental allocations |
| 📜 **Legislation** | Ordinances, resolutions, city policies |
| 📋 **Meeting Minutes** | City council records, committee proceedings |
| 📊 **Reports** | Policy studies, infrastructure analyses |
| 📝 **Administrative** | Procedures, guidelines, official notices |

### 🧪 LLM-as-Judge Evaluation System

The RAG pipeline is validated by an **LLM-as-Judge evaluation framework** that uses GPT-4 to assess chatbot response quality beyond traditional keyword matching:

```
User Question + Chatbot Answer
        │
        ▼
GPT-4 Judge Evaluation
   ├── Accuracy (factual correctness & Tulsa relevance)
   ├── Helpfulness (assists residents with civic questions)
   ├── Completeness (sufficient without verbosity)
   └── Civic Appropriateness (suitable tone for government context)
        │
        ▼
Combined Score (LLM judge + traditional metrics)
```

**Sample evaluation results:**
```
LLM-AS-JUDGE EVALUATION SUMMARY
Combined Score:     0.847 / 1.0  (Grade: B)
Traditional Score:  0.789 / 1.0
LLM Judge Score:    0.873 / 1.0
Score Improvement:  +0.084

Grade Distribution:  A: 2  B: 6  C: 2  D: 0  F: 0
```

### 🚀 Quick RAG Setup

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run database migration
cd backend && python -m alembic upgrade head

# Test the full pipeline
python scripts/test_rag_system.py
```

**Full documentation**: [`docs/RAG_SYSTEM_README.md`](docs/RAG_SYSTEM_README.md)

---

## 🏗️ Architecture

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + TypeScript + Vite + Tailwind CSS |
| **Backend** | FastAPI + Python 3.11 |
| **Database** | PostgreSQL (AWS RDS) + Redis (ElastiCache) |
| **AI/ML** | OpenAI GPT-4, `text-embedding-3-small`, RAG (ChromaDB/FAISS) |
| **Document Processing** | Multi-format (PDF, DOCX, TXT) with vector embeddings |
| **Infrastructure** | AWS ECS Fargate, RDS, S3, CloudFront |
| **CI/CD** | GitHub Actions |

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        🌐 AWS Infrastructure                     │
│                                                                  │
│  ┌────────────┐    ┌──────────────────┐    ┌─────────────────┐  │
│  │ CloudFront │───▶│  React Frontend  │    │  FastAPI Backend │  │
│  │  (CDN)     │    │  (S3 Static SPA) │    │  (ECS Fargate)  │  │
│  └────────────┘    └──────────────────┘    └────────┬────────┘  │
│                              │                       │           │
│                              └───────────┬───────────┘           │
│                                          │                       │
│                    ┌─────────────────────┼──────────────────┐    │
│                    │                     │                  │    │
│           ┌────────▼──────┐   ┌──────────▼────┐   ┌────────▼──┐ │
│           │  PostgreSQL   │   │     Redis      │   │  OpenAI   │ │
│           │  (RDS)        │   │  (Cache)       │   │  GPT-4    │ │
│           └───────────────┘   └───────────────┘   └─────┬─────┘ │
│                    │                                     │       │
│                    │         ┌───────────────────┐       │       │
│                    └────────▶│    RAG System      │◀──────┘       │
│                              │ ChromaDB / FAISS   │               │
│                              │  Vector Store      │               │
│                              └───────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Service Architecture

```
Frontend Layer
├── React 18 SPA (TypeScript)
│   ├── Pages (Meetings, Campaigns, Chatbot, etc.)
│   ├── Components (shared UI elements)
│   ├── Contexts (Auth, Notifications)
│   └── API Config (Axios + interceptors)

API Gateway Layer
├── CloudFront CDN (static assets + API routing)
└── CORS Middleware

FastAPI Application
├── Auth Endpoints (JWT)
├── Meetings Endpoints (agenda, topics, minutes)
├── Chatbot Endpoints (RAG-enhanced conversations)
├── Documents Endpoints (upload, search, manage)
├── Subscriptions Endpoints (topic-based notifications)
├── Organizations Endpoints
├── Campaigns Endpoints
└── Representatives Endpoints

Service Layer
├── ChatbotService       → OpenAI GPT-4 + RAG retrieval
├── VectorService        → ChromaDB / FAISS operations
├── DocumentProcessor    → Text extraction + chunking
├── NotificationService  → SMS (Twilio) + Email delivery
├── MeetingScraper       → Tulsa city council data ingestion
└── BaseService          → Shared DI and error handling patterns

Data Layer
├── PostgreSQL           → Structured data (meetings, users, campaigns)
├── Vector Store         → Document embeddings (semantic search)
├── Redis                → Session cache, rate limiting
└── S3                   → Document file storage
```

---

## 📁 Project Structure

```
CivicSpark_AI/
├── 🎨 frontend/              # React TypeScript application
│   ├── src/
│   │   ├── components/       # Shared UI components
│   │   ├── pages/           # Route-level page components
│   │   ├── contexts/        # React contexts (Auth, etc.)
│   │   ├── assets/images/   # Static assets & screenshots
│   │   └── config/          # API configuration
│   ├── package.json
│   └── vite.config.ts
│
├── ⚙️ backend/               # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/          # REST API endpoints
│   │   ├── models/          # SQLAlchemy database models
│   │   │   ├── meeting.py   # Meeting and agenda models
│   │   │   ├── document.py  # RAG document models
│   │   │   └── notification_preferences.py
│   │   ├── schemas/         # Pydantic response schemas
│   │   ├── services/        # Business logic
│   │   │   ├── chatbot_service.py      # AI chatbot with RAG
│   │   │   ├── vector_service.py       # Vector DB operations
│   │   │   ├── document_processing_service.py
│   │   │   └── notification_service.py
│   │   └── scrapers/        # Tulsa city council data scrapers
│   ├── alembic/             # Database migrations
│   └── requirements.txt
│
├── ☁️ aws/                   # Infrastructure as Code
│   ├── terraform/           # Terraform configurations
│   └── scripts/             # Deployment scripts
│
├── 📚 docs/                  # Documentation
│   ├── RAG_SYSTEM_README.md       # RAG architecture & usage
│   ├── CHATBOT_EVALUATION_README.md
│   ├── aws-deployment-guide.md
│   ├── TROUBLESHOOTING.md
│   └── API_DOCUMENTATION.md
│
├── 🧪 tests/
│   ├── backend/             # API tests (pytest)
│   └── frontend/            # Component tests
│
└── 🔧 scripts/
    ├── start-dev.sh
    ├── test_rag_system.py
    ├── llm_judge_evaluator.py
    └── test_production_api.sh
```

---

## 🚀 Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/kaizengrowth/CityCamp_AI.git
cd CityCamp_AI

# Backend setup
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp env.example .env
# Configure .env with your API keys
python -m app.main

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev
```

**Access points:**
- Frontend: http://localhost:3007
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Environment Variables

```bash
DATABASE_URL=postgresql://user:password@localhost/dbname
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=your_openai_api_key
SECRET_KEY=your_secret_key
```

---

## 📊 Performance Metrics

- **API Response Time**: < 500ms average
- **Database**: 40+ meetings with full AI categorization (42+ civic topics)
- **RAG Evaluation Score**: 0.847/1.0 combined (LLM-as-Judge)
- **Uptime**: 99%+ availability on AWS

---

## 🔐 Security

- HTTPS encryption for all communication
- JWT authentication with secure token handling
- AWS VPC network isolation
- IAM roles with minimal permissions
- Input validation (XSS and injection prevention)
- Database encryption at rest and in transit

---

## 📚 Documentation

| Guide | Description |
|-------|-------------|
| [RAG System Guide](docs/RAG_SYSTEM_README.md) | Document processing & vector search architecture |
| [AWS Deployment](docs/aws-deployment-guide.md) | Production infrastructure setup |
| [API Documentation](http://localhost:8000/docs) | Interactive API reference |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## Contact

Built in consultation with the Tulsa City Auditor's Office and local community organizations.

- **Email**: kaitlin.cort@owasp.org
- **GitHub**: [@kaizengrowth](https://github.com/kaizengrowth)

---

> **Note**: This demo repository is archived as we transition to a more cost-efficient architecture. The CivicSpark AI project continues in active development. All information is for educational purposes and does not constitute legal advice.
