# ============================================================================
# IAM Roles and Policies for ECS Tasks and CI/CD
# ============================================================================

# ==============================================================================
# ECS Task Execution Role
# ==============================================================================
# This role allows ECS to execute tasks: pull images, write logs, read secrets

resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${local.service_prefix}-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.service_prefix}-ecs-task-execution-role"
  }
}

# Attach Amazon's managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow ECR read access (pull images)
resource "aws_iam_role_policy_attachment" "ecs_task_execution_ecr_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

# Inline policy for Secrets Manager read access
resource "aws_iam_role_policy" "ecs_task_execution_secrets_policy" {
  name = "${local.service_prefix}-ecs-task-execution-secrets"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:beast/${var.environment}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      }
    ]
  })
}

# ==============================================================================
# ECS Task Role (Application Role)
# ==============================================================================
# This role is for the running application: S3, DynamoDB, email, etc.

resource "aws_iam_role" "ecs_task_role" {
  name = "${local.service_prefix}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${local.service_prefix}-ecs-task-role"
  }
}

# S3 access policy for file uploads/downloads
resource "aws_iam_role_policy" "ecs_task_s3_policy" {
  name = "${local.service_prefix}-ecs-task-s3"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::beast-${var.environment}-*",
          "arn:aws:s3:::beast-${var.environment}-*/*"
        ]
      }
    ]
  })
}

# CloudWatch Logs policy for application logging
resource "aws_iam_role_policy" "ecs_task_logs_policy" {
  name = "${local.service_prefix}-ecs-task-logs"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/beast-${var.environment}-*"
      }
    ]
  })
}

# SES (Simple Email Service) policy for sending emails
resource "aws_iam_role_policy" "ecs_task_ses_policy" {
  name = "${local.service_prefix}-ecs-task-ses"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      }
    ]
  })
}

# SNS (Simple Notification Service) policy for notifications
resource "aws_iam_role_policy" "ecs_task_sns_policy" {
  name = "${local.service_prefix}-ecs-task-sns"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = "*"
      }
    ]
  })
}

# DynamoDB policy (if using DynamoDB for caching)
resource "aws_iam_role_policy" "ecs_task_dynamodb_policy" {
  name = "${local.service_prefix}-ecs-task-dynamodb"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/beast-${var.environment}-*"
      }
    ]
  })
}

# ==============================================================================
# GitHub Actions OIDC Role
# ==============================================================================
# This role allows GitHub Actions to assume it via OIDC (no long-lived keys)

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # GitHub's OIDC certificate thumbprint
  # See: https://github.blog/changelog/2023-06-27-github-actions-update-on-oidc-integration-with-aws/
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1b511abead59c6ce207077c0ef5e2f7da8396f88"
  ]

  tags = {
    Name = "github-actions-oidc"
  }
}

resource "aws_iam_role" "github_actions_role" {
  name = "github-actions-beast"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:*:ref:refs/heads/*"
          }
        }
      }
    ]
  })

  tags = {
    Name = "github-actions-beast"
  }
}

# ECR push/pull policy for GitHub Actions
resource "aws_iam_role_policy" "github_actions_ecr_policy" {
  name = "github-actions-ecr"
  role = aws_iam_role.github_actions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories"
        ]
        Resource = "*"
      }
    ]
  })
}

# ECS deployment policy for GitHub Actions
resource "aws_iam_role_policy" "github_actions_ecs_policy" {
  name = "github-actions-ecs"
  role = aws_iam_role.github_actions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeContainerInstances",
          "ecs:UpdateService",
          "ecs:RegisterTaskDefinition"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM pass-role policy for GitHub Actions (to pass roles to ECS)
resource "aws_iam_role_policy" "github_actions_pass_role_policy" {
  name = "github-actions-pass-role"
  role = aws_iam_role.github_actions_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution_role.arn,
          aws_iam_role.ecs_task_role.arn
        ]
      }
    ]
  })
}

# ==============================================================================
# Outputs
# ==============================================================================

output "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_task_execution_role_name" {
  description = "Name of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution_role.name
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task application role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "ecs_task_role_name" {
  description = "Name of ECS task application role"
  value       = aws_iam_role.ecs_task_role.name
}

output "github_actions_role_arn" {
  description = "ARN of GitHub Actions OIDC role"
  value       = aws_iam_role.github_actions_role.arn
}

output "github_actions_role_name" {
  description = "Name of GitHub Actions OIDC role"
  value       = aws_iam_role.github_actions_role.name
}
