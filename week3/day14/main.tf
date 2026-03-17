terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.0"

  backend "s3" {
    bucket         = "dimitrije-tf-state-2026"
    key            = "terraform-basics/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "dimitrije-${var.project_name}-2026"
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    AccountId   = data.aws_caller_identity.current.account_id
  }
}

resource "aws_s3_bucket" "first_bucket" {
  bucket = local.bucket_name
  tags   = local.common_tags
}

resource "aws_s3_bucket_versioning" "first_bucket_versioning" {
  bucket = aws_s3_bucket.first_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}