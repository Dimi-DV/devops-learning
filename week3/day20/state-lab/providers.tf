terraform {
    required_providers {
      aws = {
        source = "hashicorp/aws"
        version = "~> 5.0"
      }
    }
    required_version = ">= 1.0"

    backend "s3" {
      bucket            = "dimitrije-tf-state-2026"
      key               = "state-lab/terraform.tfstate"
      region            = "us-east-1"
      dynamodb_table    = "terraform-locks"
      encrypt           = true
    }
}

provider "aws" {
  region = "us-east-1"
}