# Security Policy

## Protecting Secrets and Credentials

This repository must never contain:

- **API keys** (OpenAI, Geocodio, Twilio, AWS, etc.)
- **Passwords** or database connection strings with real credentials
- **Private keys** (.pem, .key, SSH keys)
- **Tokens** (JWT secrets, OAuth tokens, etc.)
- **Environment files** with real values (`.env`, `.env.local`, `.env.production`)

## Safe Practices

### Environment Variables

- Use `backend/env.example` as a template—copy to `.env` locally and never commit `.env`
- All real credentials go in:
  - **Local**: `.env` (gitignored)
  - **CI/CD**: GitHub Actions Secrets, Render/Vercel environment variables
  - **Production**: Platform secret managers (AWS Secrets Manager, etc.)

### Files That Are Safe to Commit

- `backend/env.example` – placeholder values only (`your-openai-api-key`, etc.)
- `*.tfvars.example` – Terraform variable templates
- `.env.example`, `.env.template` – frontend/env templates

### Files That Must Never Be Committed

- `.env`, `.env.local`, `.env.production`
- `secrets/` (created by deploy scripts)
- `*.tfvars` (Terraform values, often contain secrets)
- `*.pem`, `*.key`, `credentials.json`, `config.json` with secrets

## If You Accidentally Commit a Secret

1. **Rotate the secret immediately** – assume it is compromised
2. **Remove from history** – use `git filter-branch` or BFG Repo-Cleaner
3. **Force-push** (coordinate with team)
4. **Re-rotate** any secrets that may have been exposed

## Reporting Vulnerabilities

Report security issues to: **kaitlin.cort@owasp.org**

## Automated Checks

- **Gitleaks** runs on every push and PR to detect hardcoded secrets
- **.gitignore** is configured to exclude sensitive files from version control
