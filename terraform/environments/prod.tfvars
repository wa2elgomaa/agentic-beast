# Production Environment Configuration

environment = "production"
aws_region  = "us-east-1"

# VPC Configuration
vpc_cidr             = "10.0.0.0/16"
availability_zones   = 3  # Higher availability for production

# API Configuration
api_desired_count      = 3
api_cpu                = 1024
api_memory             = 2048
api_port               = 8000
api_health_check_path  = "/health"

# Frontend Configuration
frontend_desired_count     = 2
frontend_cpu               = 512
frontend_memory            = 1024
frontend_port              = 3000
frontend_health_check_path = "/"

# Celery Configuration
celery_worker_desired_count = 3
celery_worker_cpu           = 1024
celery_worker_memory        = 2048

celery_beat_desired_count = 1
celery_beat_cpu           = 512
celery_beat_memory        = 768

# Database Configuration
postgres_port = 5432
mongodb_port  = 27017
redis_port    = 6379

# Ollama (Optional LLM)
enable_ollama = false
ollama_port   = 11434

# ALB Configuration
alb_internal     = false
enable_https     = true
ssl_certificate_arn = "arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/PROD_CERT_ID"  # Update with your production certificate

# Health Checks (Stricter for production)
health_check_timeout             = 5
health_check_interval            = 15  # More frequent checks
health_check_healthy_threshold   = 3   # More strict
health_check_unhealthy_threshold = 2

# Auto-scaling
enable_autoscaling = true
api_min_capacity   = 3
api_max_capacity   = 10
api_cpu_target_utilization = 70
api_memory_target_utilization = 80

# CloudWatch
log_retention_days            = 30
container_insights_enabled    = true
enable_firelens_logging       = true

# ECR
ecr_image_scan_enabled = true
ecr_images_to_keep     = 15

# Tags
additional_tags = {
  Team       = "DevOps"
  CostCenter = "Operations"
  Compliance = "Production"
}
