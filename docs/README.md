# CivicSpark AI Documentation

## Archived Demo Repository

This documentation is for an archived demo repository. The CivicSpark AI project continues in active development with a new, more cost-efficient architecture.

## Overview

CivicSpark AI was a proof-of-concept platform designed to improve civic engagement in Tulsa, Oklahoma by connecting residents with city government through AI-powered tools.

## Core Components

### 1. AI Chatbot
- GPT-4 powered conversational interface
- RAG system for document-based answers
- Context-aware responses about city government

### 2. Meeting Management
- Automated scraping of city council meetings
- AI categorization of agenda items
- Searchable meeting minutes and records

### 3. Notification System
- Topic-based subscription service
- SMS and email delivery
- Automated meeting alerts

### 4. Community Features
- Organization directory
- Campaign management
- Representative contact tools

## Technical Architecture

### Frontend Stack
- React 18 with TypeScript
- Tailwind CSS for styling
- Vite for build tooling
- React Router for navigation

### Backend Stack
- FastAPI framework
- PostgreSQL database
- Redis caching layer
- OpenAI API integration

### Infrastructure
- AWS ECS for container orchestration
- RDS for managed PostgreSQL
- ElastiCache for Redis
- S3 and CloudFront for static assets

## Setup Instructions

For local development setup, refer to the main README.md file in the repository root.

## API Documentation

When running locally, interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

The project includes:
- Backend unit tests using pytest
- Frontend component tests
- API endpoint testing

Run tests with:
```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

## Deployment

The application was deployed to AWS using:
- Terraform for infrastructure as code
- Docker containers for application packaging
- GitHub Actions for CI/CD

Deployment configurations are available in the `aws/` directory.

## Contributing

This demo repository is archived and not accepting contributions. The CivicSpark AI project continues in active development.

## License

MIT License

## Contact

For questions about this archived demo repository or the ongoing CivicSpark AI project: kaitlin.cort@owasp.org
