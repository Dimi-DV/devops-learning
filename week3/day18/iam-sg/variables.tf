variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "iam-test"
}

variable "vpc_id" {
  description = "VPC id passed by prod vpc id via tfvars"
  type        = string
}

variable "allowed_ports" {
  description = "list of allowed ports"
  type        = list(string)
  default     = [80, 443]
}

variable "alert_email" {
  description = "Email address to receive CloudWatch alarms"
  type        = string
}