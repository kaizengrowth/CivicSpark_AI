# CivicSpark AI - Tulsa Civic Engagement Platform

**ARCHIVED DEMO REPOSITORY**: This demo repository is archived as we transition to a new architecture. The CivicSpark AI project continues in active development with a focus on cost-efficient infrastructure and core product features.

## Archive Notice

This repository represents our initial implementation and proof-of-concept that was developed through extensive consultation and UI testing with community organizations and city government offices in Tulsa. After validating the platform's value and gathering critical user feedback, we are implementing a new version with:

- Focus on core features aligned with our product roadmap
- More cost-efficient architecture to minimize server costs
- Streamlined infrastructure for better maintainability
- Simplified deployment and scaling

The project remains active and committed to improving civic engagement in Tulsa, in partnership with city agencies for neighborhood leadership.

## Overview

CivicSpark AI is a civic engagement platform that provides Tulsa residents with AI-powered tools to interact with city government, including automated notifications, meeting analytics, and community organizing features.

## Key Features

- **AI Chatbot**: Interactive assistant with city council knowledge and RAG-enhanced responses
- **Meeting Notifications**: Automated alerts for city council meetings with topic-based subscriptions
- **Meeting Analytics**: AI categorization of civic topics and searchable meeting minutes
- **Community Engagement**: Campaign tracking and neighborhood organizing tools
- **Representative Communication**: District-based representative lookup and contact tools

## Technology Stack

### Frontend
- React 18 + TypeScript + Vite
- Tailwind CSS for styling

### Backend
- FastAPI + Python 3.11
- PostgreSQL database
- Redis caching

### AI/ML
- OpenAI GPT-4 for chatbot
- RAG System using ChromaDB/FAISS for document search
- Custom categorization models

### Infrastructure
- AWS (ECS Fargate, RDS, ElastiCache, S3, CloudFront)
- Docker containerization
- GitHub Actions CI/CD

## Project Structure

```
CityCamp_AI/
├── frontend/           # React TypeScript application
│   ├── src/
│   │   ├── components/ # React components
│   │   ├── pages/      # Route components
│   │   └── contexts/   # React contexts
│   └── package.json
│
├── backend/            # FastAPI Python backend
│   ├── app/
│   │   ├── api/        # API endpoints
│   │   ├── models/     # Database models
│   │   ├── services/   # Business logic
│   │   └── scrapers/   # Data collection
│   └── requirements.txt
│
├── aws/                # Infrastructure as Code
│   └── terraform/      # Terraform configurations
│
└── tests/              # Test suites
    ├── backend/        # API tests
    └── frontend/       # Component tests
```

## Local Development

### Prerequisites
- Node.js >= 18.0.0
- Python >= 3.11.0
- PostgreSQL
- Docker (optional)

### Quick Start

```bash
# Clone repository
git clone https://github.com/kaizengrowth/CityCamp_AI.git
cd CityCamp_AI

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp env.example .env
# Configure .env with your settings
python -m app.main

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev
```

### Access Points
- Frontend: http://localhost:3007
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## Environment Variables

Create a `.env` file in the backend directory with the following variables:

```
DATABASE_URL=postgresql://user:password@localhost/dbname
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=your_openai_api_key
SECRET_KEY=your_secret_key
```

## Testing

```bash
# Frontend tests
cd frontend
npm test

# Backend tests
cd backend
pytest tests/
```

## Architecture

The application follows a layered architecture with clear separation of concerns:

- **API Layer**: FastAPI with standardized REST endpoints
- **Service Layer**: Business logic with dependency injection
- **Data Layer**: PostgreSQL for structured data, Vector store for embeddings
- **External APIs**: OpenAI for AI capabilities, Twilio for SMS

## Contributing

This demo repository is archived and not accepting contributions. For information about the ongoing CivicSpark AI project, please contact us directly.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

Built in consultation with the Tulsa City Auditor's Office and local community organizations.

## Contact

For questions about this archived project: kaitlin.cort@owasp.org

---

**Note**: This demo repository is archived as we transition to a more cost-efficient architecture. The CivicSpark AI project continues in active development. All information provided is for educational purposes and does not constitute legal advice.
