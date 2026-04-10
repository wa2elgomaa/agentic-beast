variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Number of availability zones"
  type        = number
  default     = 2
}

# ECS Configuration
variable "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
  default     = ""
}

variable "container_insights_enabled" {
  description = "Enable Container Insights monitoring"
  type        = bool
  default     = true
}

# Backend API Configuration
variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
  validation {
    condition     = var.api_desired_count >= 1 && var.api_desired_count <= 5
    error_message = "API desired count must be between 1 and 5."
  }
}

variable "api_cpu" {
  description = "CPU units for API task (256, 512, 1024, 2048, 4096)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory (MB) for API task (512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192)"
  type        = number
  default     = 1024
}

variable "api_port" {
  description = "Port for API container"
  type        = number
  default     = 8000
}

# Frontend Configuration
variable "frontend_desired_count" {
  description = "Desired number of frontend tasks"
  type        = number
  default     = 2
}

variable "frontend_cpu" {
  description = "CPU units for frontend task"
  type        = number
  default     = 256
}

variable "frontend_memory" {
  description = "Memory (MB) for frontend task"
  type        = number
  default     = 512
}

variable "frontend_port" {
  description = "Port for frontend container"
  type        = number
  default     = 3000
}

# Celery Worker Configuration
variable "celery_worker_desired_count" {
  description = "Desired number of Celery worker tasks"
  type        = number
  default     = 2
}

variable "celery_worker_cpu" {
  description = "CPU units for Celery worker task"
  type        = number
  default     = 512
}

variable "celery_worker_memory" {
  description = "Memory (MB) for Celery worker task"
  type        = number
  default     = 1024
}

# Celery Beat Configuration
variable "celery_beat_desired_count" {
  description = "Desired number of Celery beat tasks (should be 1)"
  type        = number
  default     = 1
}

variable "celery_beat_cpu" {
  description = "CPU units for Celery beat task"
  type        = number
  default     = 256
}

variable "celery_beat_memory" {
  description = "Memory (MB) for Celery beat task"
  type        = number
  default     = 512
}

# Database Configuration
variable "postgres_port" {
  description = "PostgreSQL port"
  type        = number
  default     = 5432
}

variable "mongodb_port" {
  description = "MongoDB port"
  type        = number
  default     = 27017
}

variable "redis_port" {
  description = "Redis port"
  type        = number
  default     = 6379
}

# Ollama Configuration (Optional LLM service)
variable "enable_ollama" {
  description = "Enable Ollama LLM service"
  type        = bool
  default     = false
}

variable "ollama_port" {
  description = "Ollama port"
  type        = number
  default     = 11434
}

# ALB Configuration
variable "alb_internal" {
  description = "Make ALB internal (private)"
  type        = bool
  default     = false
}

variable "enable_https" {
  description = "Enable HTTPS on ALB"
  type        = bool
  default     = false
}

variable "ssl_certificate_arn" {
  description = "ARN of SSL certificate for HTTPS (required if enable_https=true)"
  type        = string
  default     = ""
}

# Health Check Configuration
variable "api_health_check_path" {
  description = "Health check path for API"
  type        = string
  default     = "/health"
}

variable "frontend_health_check_path" {
  description = "Health check path for frontend"
  type        = string
  default     = "/"
}

variable "health_check_timeout" {
  description = "Health check timeout in seconds"
  type        = number
  default     = 5
}

variable "health_check_interval" {
  description = "Health check interval in seconds"
  type        = number
  default     = 30
}

variable "health_check_healthy_threshold" {
  description = "Number of consecutive health checks successes required"
  type        = number
  default     = 2
}

variable "health_check_unhealthy_threshold" {
  description = "Number of consecutive health check failures required"
  type        = number
  default     = 3
}

# Auto-scaling Configuration
variable "enable_autoscaling" {
  description = "Enable auto-scaling for ECS services"
  type        = bool
  default     = true
}

variable "api_min_capacity" {
  description = "Minimum number of API tasks for auto-scaling"
  type        = number
  default     = 2
}

variable "api_max_capacity" {
  description = "Maximum number of API tasks for auto-scaling"
  type        = number
  default     = 5
}

variable "api_cpu_target_utilization" {
  description = "Target CPU utilization for API auto-scaling"
  type        = number
  default     = 70
}

variable "api_memory_target_utilization" {
  description = "Target memory utilization for API auto-scaling"
  type        = number
  default     = 80
}

# CloudWatch Logging
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "enable_firelens_logging" {
  description = "Enable FireLens for advanced logging"
  type        = bool
  default     = false
}

# ECR Configuration
variable "ecr_image_scan_enabled" {
  description = "Enable ECR image scanning"
  type        = bool
  default     = true
}

variable "ecr_images_to_keep" {
  description = "Number of Docker images to keep in ECR"
  type        = number
  default     = 10
}

# Secrets
variable "database_secrets" {
  description = "Database passwords and credentials"
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "api_secrets" {
  description = "API secrets (JWT, API keys, etc.)"
  type        = map(string)
  sensitive   = true
  default     = {}
}

# Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
