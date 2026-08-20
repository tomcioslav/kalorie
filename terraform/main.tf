terraform {
  required_version = ">= 1.11"

  backend "s3" {
    bucket       = "calorie-tracker-tfstate-726024099471"
    key          = "calorie-tracker/terraform.tfstate"
    region       = "eu-central-1"
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "calorie-tracker"
    }
  }
}
