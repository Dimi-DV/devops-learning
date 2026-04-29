module "vpc" {
  source = "../../day15/aws-vpc-terraform/modules/vpc"

  project_name       = var.project_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  allowed_ssh_cidrs  = var.allowed_ssh_cidrs
  create_nat         = false
}

