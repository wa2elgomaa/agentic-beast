# ============================================================================
# AWS Secrets Manager - Encrypted Credential Storage
# ============================================================================

# ==============================================================================
# Database Secrets
# ==============================================================================

# PostgreSQL Credentials
resource "aws_secretsmanager_secret" "postgres" {
  name                    = "beast/${var.environment}/db/postgres"
  description             = "PostgreSQL database credentials for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-postgres"
  }
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  secret_string = jsonencode({
    username = try(var.database_secrets["postgres_username"], "beast")
    password = try(var.database_secrets["postgres_password"], "changeme")
    hostname = "localhost"  # Will be updated to container/RDS hostname
    port     = var.postgres_port
    database = "beast"
    engine   = "postgresql"
  })
}

# MongoDB Credentials
resource "aws_secretsmanager_secret" "mongodb" {
  name                    = "beast/${var.environment}/db/mongodb"
  description             = "MongoDB database credentials for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-mongodb"
  }
}

resource "aws_secretsmanager_secret_version" "mongodb" {
  secret_id = aws_secretsmanager_secret.mongodb.id
  secret_string = jsonencode({
    username = try(var.database_secrets["mongodb_username"], "admin")
    password = try(var.database_secrets["mongodb_password"], "changeme")
    hostname = "localhost"  # Will be updated to container/Atlas hostname
    port     = var.mongodb_port
    database = "beast"
    engine   = "mongodb"
  })
}

# Redis Password
resource "aws_secretsmanager_secret" "redis" {
  name                    = "beast/${var.environment}/cache/redis"
  description             = "Redis password for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-redis"
  }
}

resource "aws_secretsmanager_secret_version" "redis" {
  secret_id = aws_secretsmanager_secret.redis.id
  secret_string = jsonencode({
    hostname = "localhost"  # Will be updated to container/ElastiCache hostname
    port     = var.redis_port
    password = try(var.database_secrets["redis_password"], "changeme")
    database = "0"
  })
}

# ==============================================================================
# API and Application Secrets
# ==============================================================================

# JWT Secret Key
resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "beast/${var.environment}/api/jwt"
  description             = "JWT signing secret for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id = aws_secretsmanager_secret.jwt_secret.id
  secret_string = jsonencode({
    secret_key = try(var.api_secrets["jwt_secret_key"], "your-secret-key-change-in-production")
    algorithm  = "HS256"
  })
}

# OpenAI API Key
resource "aws_secretsmanager_secret" "openai" {
  name                    = "beast/${var.environment}/providers/openai"
  description             = "OpenAI API key for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-openai"
  }
}

resource "aws_secretsmanager_secret_version" "openai" {
  secret_id = aws_secretsmanager_secret.openai.id
  secret_string = jsonencode({
    api_key = try(var.api_secrets["main_api_key"], "sk-changeme")
    model   = "gpt-4"
  })
}

# Gmail Credentials (for email ingestion)
resource "aws_secretsmanager_secret" "gmail" {
  name                    = "beast/${var.environment}/gmail"
  description             = "Gmail API credentials for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-gmail"
  }
}

resource "aws_secretsmanager_secret_version" "gmail" {
  secret_id = aws_secretsmanager_secret.gmail.id
  secret_string = jsonencode({
    client_email        = try(var.api_secrets["gmail_client_email"], "your-service-account@your-project.iam.gserviceaccount.com")
    private_key         = try(var.api_secrets["gmail_private_key"], "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n")
    private_key_id      = try(var.api_secrets["gmail_private_key_id"], "key-id")
    project_id          = try(var.api_secrets["gmail_project_id"], "project-id")
    type                = "service_account"
    client_id           = try(var.api_secrets["gmail_client_id"], "")
  })
}

# Sentry DSN (Error Tracking)
resource "aws_secretsmanager_secret" "sentry" {
  name                    = "beast/${var.environment}/observability/sentry"
  description             = "Sentry DSN for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-sentry"
  }
}

resource "aws_secretsmanager_secret_version" "sentry" {
  secret_id = aws_secretsmanager_secret.sentry.id
  secret_string = jsonencode({
    dsn             = try(var.api_secrets["sentry_dsn"], "https://examplePublicKey@o0.ingest.sentry.io/0")
    environment     = var.environment
    traces_sample_rate = var.environment == "production" ? 0.1 : 1.0
  })
}

# AWS Bedrock (Alternative LLM Provider)
resource "aws_secretsmanager_secret" "bedrock" {
  name                    = "beast/${var.environment}/providers/bedrock"
  description             = "AWS Bedrock configuration for Beast ${var.environment}"
  recovery_window_in_days = var.environment == "production" ? 30 : 7

  tags = {
    Name = "beast-${var.environment}-bedrock"
  }
}

resource "aws_secretsmanager_secret_version" "bedrock" {
  secret_id = aws_secretsmanager_secret.bedrock.id
  secret_string = jsonencode({
    region         = data.aws_region.current.name
    model_id       = "anthropic.claude-3-sonnet-20240229-v1:0"
    enable_bedrock = try(var.api_secrets["enable_bedrock"], "false")
  })
}

# ==============================================================================
# Outputs
# ==============================================================================

output "postgres_secret_arn" {
  description = "ARN of PostgreSQL secret"
  value       = aws_secretsmanager_secret.postgres.arn
}

output "mongodb_secret_arn" {
  description = "ARN of MongoDB secret"
  value       = aws_secretsmanager_secret.mongodb.arn
}

output "redis_secret_arn" {
  description = "ARN of Redis secret"
  value       = aws_secretsmanager_secret.redis.arn
}

output "jwt_secret_arn" {
  description = "ARN of JWT secret"
  value       = aws_secretsmanager_secret.jwt_secret.arn
}

output "openai_secret_arn" {
  description = "ARN of OpenAI secret"
  value       = aws_secretsmanager_secret.openai.arn
}

output "gmail_secret_arn" {
  description = "ARN of Gmail secret"
  value       = aws_secretsmanager_secret.gmail.arn
}

output "sentry_secret_arn" {
  description = "ARN of Sentry secret"
  value       = aws_secretsmanager_secret.sentry.arn
}

output "bedrock_secret_arn" {
  description = "ARN of Bedrock secret"
  value       = aws_secretsmanager_secret.bedrock.arn
}

# All secrets can be referenced in ECS task definitions using valueFrom with the secret ARN
# Example in task definition:
# secrets = [{
#   name      = "DATABASE_URL"
#   valueFrom = aws_secretsmanager_secret.postgres.arn
# }]
