# =============================================================================
# REQUIRED INPUTS
# The caller MUST provide these. No defaults — forces explicit decision per env.
# =============================================================================

variable "project_name" {
  description = "Project identifier used in resource names and tags"
  type        = string
}

variable "environment" {
  description = "Environment discriminator (dev, staging, prod) used in names and tags"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC (e.g. 10.0.0.0/16 for dev, 10.1.0.0/16 for prod)"
  type        = string
}

variable "availability_zones" {
  description = "Availability zones for subnet placement"
  type        = list(string)
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the web security group"
  type        = list(string)
}

variable "create_nat" {
  description = "Whether to create a NAT Gateway for private subnet internet egress. Set false to save ~$32/month in non-prod environments."
  type        = bool
  default     = true
}