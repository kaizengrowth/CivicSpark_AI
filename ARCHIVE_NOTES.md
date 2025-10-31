# Archive Notes

## Repository Status

This demo repository has been cleaned and prepared for archival on October 31, 2025.

## Project Status

**The CivicSpark AI project is ongoing and in active development.** This specific repository is being archived as we transition to a new, more cost-efficient architecture.

### Why This Repository is Archived

This repository represents our initial proof-of-concept that was developed through extensive consultation and UI testing with:
- Tulsa City Auditor's Office
- Local community organizations
- City Council offices
- Tulsa residents

After successfully validating the platform's value and gathering critical user feedback, we are implementing a new version focused on:
- Cost-efficient architecture to minimize server costs
- Streamlined infrastructure for better maintainability
- Core features aligned with our product roadmap
- Simplified deployment and scaling

## Cleanup Actions Performed

### Sensitive Data Removed

- All log files (*.log, logs/ directory)
- Database files (*.db, *.sqlite3)
- Data exports (meetings_export.csv, meetings_export.json)
- Terraform state files (terraform.tfstate*)
- AWS deployment scripts with hardcoded values
- User data scripts with configuration details
- Document storage directories (backend/storage/docs, backend/storage/pdfs)
- Test document collections
- Terraform variable files with actual values (terraform.tfvars)


### Files Added to .gitignore

- All sensitive deployment files
- Documentation directories
- Database and log files
- Test documents and PDFs
- Terraform state and plan files
- Data export files

## Repository Structure

```
CityCamp_AI/
├── README.md              # Main documentation
├── LICENSE                # MIT License
├── CONTRIBUTING.md        # Archive notice
├── ARCHIVE_NOTES.md       # This file
├── .gitignore             # Comprehensive exclusions
│
├── frontend/              # React application
├── backend/               # FastAPI application
├── aws/                   # Infrastructure configs
├── tests/                 # Test suites
├── scripts/               # Utility scripts
└── docs/                  # Technical documentation
```

## Security Status

- No API keys or credentials in repository
- No production URLs or IP addresses exposed
- No personally identifiable information
- All deployment-specific values removed
- Terraform state files deleted

## Use Cases

This archived demo repository can be used for:

1. Reference implementation of civic tech platform
2. Learning React + FastAPI architecture
3. Example of RAG system implementation
4. Study of civic engagement features
5. Template for similar projects

## Not Included

The following are intentionally excluded:

- Production database contents
- User data and PII
- API credentials and secrets
- Deployment credentials
- Infrastructure state
- Large media files
- Test documents and PDFs

## Contact

For questions about this archived demo repository: kaitlin.cort@owasp.org

For information about the ongoing CivicSpark AI project: kaitlin.cort@owasp.org

## License

MIT License - See LICENSE file for full text

---

**Archive Date**: October 31, 2025
**Archive Reason**: Transition to cost-efficient architecture after successful consultation and testing phase
**Project Status**: Ongoing in active development
**Demo Repository Status**: Safe for public archival
