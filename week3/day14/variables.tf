variable "project_name" {
    type        = string
    description = "project name used in resource naming and tags"
    default     = "tf-basics"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
    type        = string
    description = "AWS region to deploy into"
    default     = "us-east-1"
}