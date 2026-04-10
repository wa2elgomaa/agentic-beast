# ============================================================================
# Amazon ECR (Elastic Container Registry) Repositories
# ============================================================================

# ==============================================================================
# Backend Repository
# ==============================================================================

resource "aws_ecr_repository" "backend" {
  name                 = "${local.service_prefix}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = var.ecr_image_scan_enabled
  }

  tags = {
    Name = "${local.service_prefix}-backend"
  }
}

# Lifecycle policy for backend repository
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last N untagged images"
        selection = {
          tagStatus       = "untagged"
          countType       = "imageCountMoreThan"
          countNumber     = var.ecr_images_to_keep
          countUnit       = "days"
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last N tagged images"
        selection = {
          tagStatus       = "tagged"
          tagPrefixList   = ["latest", "prod", "staging"]
          countType       = "imageCountMoreThan"
          countNumber     = var.ecr_images_to_keep
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 3
        description  = "Delete images older than 30 days"
        selection = {
          tagStatus       = "any"
          countType       = "sinceImagePushed"
          countNumber     = 30
          countUnit       = "days"
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ==============================================================================
# Frontend Repository
# ==============================================================================

resource "aws_ecr_repository" "frontend" {
  name                 = "${local.service_prefix}-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = var.ecr_image_scan_enabled
  }

  tags = {
    Name = "${local.service_prefix}-frontend"
  }
}

# Lifecycle policy for frontend repository
resource "aws_ecr_lifecycle_policy" "frontend" {
  repository = aws_ecr_repository.frontend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last N untagged images"
        selection = {
          tagStatus       = "untagged"
          countType       = "imageCountMoreThan"
          countNumber     = var.ecr_images_to_keep
          countUnit       = "days"
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last N tagged images"
        selection = {
          tagStatus       = "tagged"
          tagPrefixList   = ["latest", "prod", "staging"]
          countType       = "imageCountMoreThan"
          countNumber     = var.ecr_images_to_keep
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 3
        description  = "Delete images older than 30 days"
        selection = {
          tagStatus       = "any"
          countType       = "sinceImagePushed"
          countNumber     = 30
          countUnit       = "days"
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ==============================================================================
# Outputs
# ==============================================================================

output "backend_repository_url" {
  description = "URL of backend ECR repository"
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_repository_arn" {
  description = "ARN of backend ECR repository"
  value       = aws_ecr_repository.backend.arn
}

output "backend_repository_name" {
  description = "Name of backend ECR repository"
  value       = aws_ecr_repository.backend.name
}

output "frontend_repository_url" {
  description = "URL of frontend ECR repository"
  value       = aws_ecr_repository.frontend.repository_url
}

output "frontend_repository_arn" {
  description = "ARN of frontend ECR repository"
  value       = aws_ecr_repository.frontend.arn
}

output "frontend_repository_name" {
  description = "Name of frontend ECR repository"
  value       = aws_ecr_repository.frontend.name
}
