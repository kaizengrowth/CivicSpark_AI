# AWS Infrastructure

## Overview

This directory contains Infrastructure as Code (IaC) configurations for deploying CivicSpark AI to AWS.

## Contents

- `terraform/` - Terraform configurations for AWS resources

## Infrastructure Components

The application was deployed using:

- **ECS Fargate**: Container orchestration
- **RDS PostgreSQL**: Managed database
- **ElastiCache Redis**: Caching layer
- **S3**: Static file storage
- **CloudFront**: CDN for frontend assets
- **Application Load Balancer**: Traffic distribution

## Terraform Setup

### Prerequisites

- Terraform >= 1.0
- AWS CLI configured with appropriate credentials
- Docker for building images

### Variables

Key variables are defined in `terraform/variables.tf`. Create a `terraform.tfvars` file with your values:

```hcl
aws_region = "us-east-1"
project_name = "civicspark"
environment = "production"
```

### Deployment

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### Cleanup

```bash
terraform destroy
```

## Security

- All credentials should be stored in AWS Secrets Manager or Parameter Store
- Never commit sensitive values to version control
- Use IAM roles with minimal required permissions
- Enable encryption at rest and in transit

## Note

This is an archived project. The infrastructure configurations are provided for reference only.
