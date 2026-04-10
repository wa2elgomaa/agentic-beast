terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment after first apply to store state in S3
  # backend "s3" {
  #   bucket         = "beast-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "beast-terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "the-beast"
      ManagedBy   = "terraform"
      CreatedAt   = timestamp()
    }
  }
}

# Local values
locals {
  common_tags = {
    Environment = var.environment
    Project     = "the-beast"
    ManagedBy   = "terraform"
  }

  container_name_api      = "beast-api"
  container_name_frontend = "beast-frontend"
  container_name_worker   = "beast-celery-worker"
  container_name_beat     = "beast-celery-beat"
  container_name_postgres = "beast-postgres"
  container_name_mongodb  = "beast-mongodb"
  container_name_redis    = "beast-redis"
  container_name_ollama   = "beast-ollama"

  # Resource naming
  cluster_name     = "beast-${var.environment}-cluster"
  service_prefix   = "beast-${var.environment}"
  alb_name         = "beast-${var.environment}-alb"
  tg_api_name      = "beast-${var.environment}-api-tg"
  tg_frontend_name = "beast-${var.environment}-frontend-tg"
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
