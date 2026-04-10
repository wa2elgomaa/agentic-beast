# ============================================================================
# Terraform Outputs
# ============================================================================
# These outputs are displayed after terraform apply and used for deployments

# ==============================================================================
# VPC Outputs (from vpc.tf)
# ==============================================================================

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "CIDR block of VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "Security group ID for ECS tasks"
  value       = aws_security_group.ecs_tasks.id
}

# ==============================================================================
# IAM Outputs (from iam.tf)
# ==============================================================================

output "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task application role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "github_actions_role_arn" {
  description = "ARN of GitHub Actions OIDC role (use for GitHub Actions secrets)"
  value       = aws_iam_role.github_actions_role.arn
}

# ==============================================================================
# ECR Outputs (from ecr.tf)
# ==============================================================================

output "backend_ecr_repository_url" {
  description = "URL of backend ECR repository (for docker push)"
  value       = aws_ecr_repository.backend.repository_url
}

output "backend_ecr_repository_name" {
  description = "Name of backend ECR repository"
  value       = aws_ecr_repository.backend.name
}

output "backend_ecr_repository_arn" {
  description = "ARN of backend ECR repository"
  value       = aws_ecr_repository.backend.arn
}

output "frontend_ecr_repository_url" {
  description = "URL of frontend ECR repository (for docker push)"
  value       = aws_ecr_repository.frontend.repository_url
}

output "frontend_ecr_repository_name" {
  description = "Name of frontend ECR repository"
  value       = aws_ecr_repository.frontend.name
}

output "frontend_ecr_repository_arn" {
  description = "ARN of frontend ECR repository"
  value       = aws_ecr_repository.frontend.arn
}

# ==============================================================================
# ALB Outputs (from alb.tf)
# ==============================================================================

output "alb_dns_name" {
  description = "DNS name of the load balancer (use this for API access)"
  value       = aws_lb.main.dns_name
}

output "alb_arn" {
  description = "ARN of the load balancer"
  value       = aws_lb.main.arn
}

output "alb_zone_id" {
  description = "Zone ID of the load balancer (for Route53)"
  value       = aws_lb.main.zone_id
}

output "api_target_group_arn" {
  description = "ARN of API target group"
  value       = aws_lb_target_group.api.arn
}

output "api_target_group_name" {
  description = "Name of API target group"
  value       = aws_lb_target_group.api.name
}

output "frontend_target_group_arn" {
  description = "ARN of frontend target group"
  value       = aws_lb_target_group.frontend.arn
}

output "frontend_target_group_name" {
  description = "Name of frontend target group"
  value       = aws_lb_target_group.frontend.name
}

# ==============================================================================
# ECS Outputs (from ecs.tf)
# ==============================================================================

output "ecs_cluster_id" {
  description = "ID of ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_name" {
  description = "Name of ECS cluster (use in GitHub Actions deployments)"
  value       = aws_ecs_cluster.main.name
}

output "ecs_cluster_arn" {
  description = "ARN of ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "api_service_name" {
  description = "Name of API ECS service"
  value       = aws_ecs_service.api.name
}

output "api_service_arn" {
  description = "ARN of API ECS service"
  value       = aws_ecs_service.api.arn
}

output "frontend_service_name" {
  description = "Name of frontend ECS service"
  value       = aws_ecs_service.frontend.name
}

output "frontend_service_arn" {
  description = "ARN of frontend ECS service"
  value       = aws_ecs_service.frontend.arn
}

output "celery_worker_service_name" {
  description = "Name of Celery worker ECS service"
  value       = aws_ecs_service.celery_worker.name
}

output "celery_beat_service_name" {
  description = "Name of Celery beat ECS service"
  value       = aws_ecs_service.celery_beat.name
}

output "api_task_definition_arn" {
  description = "ARN of API task definition"
  value       = aws_ecs_task_definition.api.arn
}

output "api_task_definition_family" {
  description = "Family of API task definition"
  value       = aws_ecs_task_definition.api.family
}

output "frontend_task_definition_arn" {
  description = "ARN of frontend task definition"
  value       = aws_ecs_task_definition.frontend.arn
}

output "frontend_task_definition_family" {
  description = "Family of frontend task definition"
  value       = aws_ecs_task_definition.frontend.family
}

# ==============================================================================
# CloudWatch Logs Outputs
# ==============================================================================

output "api_log_group_name" {
  description = "CloudWatch log group name for API"
  value       = aws_cloudwatch_log_group.ecs_api.name
}

output "frontend_log_group_name" {
  description = "CloudWatch log group name for frontend"
  value       = aws_cloudwatch_log_group.ecs_frontend.name
}

output "celery_worker_log_group_name" {
  description = "CloudWatch log group name for Celery worker"
  value       = aws_cloudwatch_log_group.ecs_celery_worker.name
}

output "celery_beat_log_group_name" {
  description = "CloudWatch log group name for Celery beat"
  value       = aws_cloudwatch_log_group.ecs_celery_beat.name
}

# ==============================================================================
# Secrets Manager Outputs
# ==============================================================================

output "postgres_secret_arn" {
  description = "ARN of PostgreSQL credentials secret"
  value       = aws_secretsmanager_secret.postgres.arn
  sensitive   = true
}

output "mongodb_secret_arn" {
  description = "ARN of MongoDB credentials secret"
  value       = aws_secretsmanager_secret.mongodb.arn
  sensitive   = true
}

output "redis_secret_arn" {
  description = "ARN of Redis credentials secret"
  value       = aws_secretsmanager_secret.redis.arn
  sensitive   = true
}

output "jwt_secret_arn" {
  description = "ARN of JWT secret"
  value       = aws_secretsmanager_secret.jwt_secret.arn
  sensitive   = true
}

output "openai_secret_arn" {
  description = "ARN of OpenAI API secret"
  value       = aws_secretsmanager_secret.openai.arn
  sensitive   = true
}

output "gmail_secret_arn" {
  description = "ARN of Gmail credentials secret"
  value       = aws_secretsmanager_secret.gmail.arn
  sensitive   = true
}

output "sentry_secret_arn" {
  description = "ARN of Sentry DSN secret"
  value       = aws_secretsmanager_secret.sentry.arn
  sensitive   = true
}

output "bedrock_secret_arn" {
  description = "ARN of Bedrock configuration secret"
  value       = aws_secretsmanager_secret.bedrock.arn
  sensitive   = true
}

# ==============================================================================
# Useful Information for Deployment
# ==============================================================================

output "deployment_instructions" {
  description = "Instructions for deploying to this environment"
  value = "API URL: http://${aws_lb.main.dns_name}/api/v1\nFrontend URL: http://${aws_lb.main.dns_name}\nCluster: ${aws_ecs_cluster.main.name}\nECR Backend: ${aws_ecr_repository.backend.repository_url}\nECR Frontend: ${aws_ecr_repository.frontend.repository_url}\n\nFor GitHub Actions, set AWS_ROLE_TO_ASSUME to: ${aws_iam_role.github_actions_role.arn}"
}

output "aws_account_id" {
  description = "AWS Account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS Region"
  value       = data.aws_region.current.name
}

output "environment" {
  description = "Deployment environment"
  value       = var.environment
}
