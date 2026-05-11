# AWS Infrastructure & DevOps Projects

[![CI](https://github.com/Dimi-DV/devops-learning/actions/workflows/ci.yml/badge.svg)](https://github.com/Dimi-DV/devops-learning/actions/workflows/ci.yml)
[![Terraform VPC](https://github.com/Dimi-DV/devops-learning/actions/workflows/terraform-vpc.yml/badge.svg)](https://github.com/Dimi-DV/devops-learning/actions/workflows/terraform-vpc.yml)

Production-style AWS infrastructure built with Terraform, containerized services running on ECS Fargate, and CI/CD pipelines that build, test, and push images through GitHub Actions with OIDC-authenticated AWS access. Each project is end-to-end deployable and ships with a README covering architecture, deploy steps, costs, design decisions, and the gaps between this implementation and a production deployment.

## Featured projects

- **[Multi-AZ web stack on AWS](week3/day19/full-stack/)** — ALB + Auto Scaling Group across two AZs, IAM role for instances writing to CloudWatch Logs, S3 bucket for ALB access logs with versioning and encryption, CloudWatch alarm wired to SNS email alerts. All Terraform, all wired together, all destroyable in one command.
- **[Production VPC as a Terraform module](week3/day15/aws-vpc-terraform/)** — VPC with public/private subnets across two AZs, refactored into a reusable module using `for_each`, `cidrsubnet()`, and conditional NAT. Multi-environment structure with separate `dev` and `prod` callers.
- **[Containerized Flask app on ECS Fargate](week4/day23/healthy-app/)** — Multi-stage Dockerfile with non-root user and healthcheck, deployed to ECS Fargate behind a multi-AZ ALB, pushed through a GitHub Actions pipeline (lint → matrix test → build → ECR push with OIDC).
- **[Flask + Postgres multi-container app](week4/day22/compose-app/)** — Two-service Docker Compose application demonstrating service-name DNS, healthcheck-gated startup, and persistent state via named volumes.

## CI/CD

Three workflows live in `.github/workflows/`:

- **`ci.yml`** — Lint (flake8) → matrix test (Python 3.10/3.11/3.12) → build and push to ECR. Triggered by changes to the `healthy-app/` directory. Path-based filters keep unrelated commits from running the pipeline.
- **`terraform-vpc.yml`** — `terraform fmt` and `terraform validate` always; `terraform plan` on pull requests with the plan output posted back as a PR comment; `terraform apply` on merge to `main`.
- **`docker-build-push.yml`** — Reusable workflow consumed by `ci.yml` for the Docker build and ECR push step. Tags images with both the commit SHA and `latest`.

Both pipelines authenticate to AWS via OIDC — no long-lived access keys stored in repo secrets. The IAM roles trust only OIDC tokens originating from this repository.

## Repository structure

The repository is organized by week of work. Each week covers a topic area; each day's directory contains the code, configuration, and notes for that day.

- **Week 1 — Linux & networking foundations.** Filesystem and permissions, processes and systemd, package management, subnetting and DNS, TCP/IP and ports, HTTP and TLS, firewalls, SSH, text processing, Python scripting for sysadmin.
- **Week 2 — AWS core services.** IAM (users, roles, policies, instance profiles), VPC architecture, EC2, S3, CloudWatch, ALB + Auto Scaling Groups, RDS and DynamoDB, Route 53.
- **Week 3 — Infrastructure as Code with Terraform.** HCL fundamentals, remote state with S3 + DynamoDB locking, the production VPC built and refactored into a reusable module, the full-stack web application as code with monitoring and IAM, advanced patterns (`for_each`, `count`, `cidrsubnet`, conditionals, `default_tags`).
- **Week 4 — Containers and CI/CD.** Docker fundamentals and multi-stage builds, Docker Compose with healthcheck-gated startup, ECR with OIDC-authenticated push from GitHub Actions, ECS Fargate deployment with task definitions and services, Terraform-in-CI (plan-on-PR with PR comments, apply-on-merge), Kubernetes introduction with kind.

## Tooling

Terraform 1.14 · Python 3.12 · Docker Engine 29 · AWS CLI v2 · GitHub Actions · GitHub CLI · Ubuntu 24.04 (UTM VM on Apple Silicon)
