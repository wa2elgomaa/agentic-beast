# AWS ECS CI/CD Deployment - Complete Setup Guide

**Last Updated:** 2026-04-10
**Status:** Phase 1 Complete (40% of implementation)

---

## ✅ COMPLETED

### GitHub Actions Workflows (4 files)
- ✅ `.github/workflows/ci.yml` - Build, test, lint
- ✅ `.github/workflows/build-push-ecs.yml` - Build and push to ECR
- ✅ `.github/workflows/deploy-ecs.yml` - Deploy to dev/staging
- ✅ `.github/workflows/deploy-ecs-prod.yml` - Production deployment with approvals

### Terraform Infrastructure (3 files)
- ✅ `terraform/main.tf` - Provider configuration and locals
- ✅ `terraform/variables.tf` - All input variables for configuration
- ✅ `terraform/vpc.tf` - VPC, subnets, security groups, NAT gateways

---

## 🚀 REMAINING IMPLEMENTATION

### Phase 2: IAM Roles and Permissions (terraform/iam.tf)

**File Path:** `terraform/iam.tf` (180-200 lines)

**Components to Create:**

1. **ECS Task Execution Role**
   - Allows ECS tasks to pull images from ECR: `AmazonEC2ContainerRegistryPowerUser`
   - Allows push logs to CloudWatch: `CloudWatchLogsFullAccess`
   - Allows read secrets from Secrets Manager: Custom inline policy
   - Resource: `aws_iam_role.ecs_task_execution_role`

2. **ECS Task Role (Application Role)**
   - Allows S3 access for file uploads/downloads
   - Allows DynamoDB access (if needed for caching)
   - Allows SES/SNS for email notifications
   - Resource: `aws_iam_role.ecs_task_role`

3. **GitHub Actions OIDC Role**
   - Allows GitHub Actions to assume role for CI/CD
   - Permissions: ECR push/pull, ECS deploy, CloudFormation updates
   - Federated identity (GitHub provider)
   - Resource: `aws_iam_role.github_actions_role`

**Key Policies:**
```hcl
# ECS task execution inline policy for secrets
policy = jsonencode({
  Version = "2012-10-17"
  Statement = [
    {
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ]
      Resource = "arn:aws:secretsmanager:*:ACCOUNT_ID:secret:beast/*"
    }
  ]
})
```

### Phase 3: ECR Repositories (terraform/ecr.tf)

**File Path:** `terraform/ecr.tf` (80-100 lines)

**Components:**

1. **Backend Repository**
   - Repository name: `beast-backend`
   - Image scanning: enabled
   - Lifecycle policy: Keep last 10 images, delete old tags
   - Resource: `aws_ecr_repository.backend`

2. **Frontend Repository**
   - Repository name: `beast-frontend`
   - Image scanning: enabled
   - Lifecycle policy: Keep last 10 images
   - Resource: `aws_ecr_repository.frontend`

3. **Lifecycle Policies**
   - Delete untagged images older than 30 days
   - Keep only last N images per repository
   - Resource: `aws_ecr_lifecycle_policy.backend`, `aws_ecr_lifecycle_policy.frontend`

**Example Lifecycle Policy:**
```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 images",
      "selection": {
        "tagStatus": "tagged",
        "tagPrefixList": ["latest"],
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
```

### Phase 4: Application Load Balancer (terraform/alb.tf)

**File Path:** `terraform/alb.tf` (200-250 lines)

**Components:**

1. **Load Balancer**
   - Type: Application Load Balancer (ALB)
   - Internal/External: Based on `var.alb_internal`
   - Subnets: Public subnets across AZs
   - Security group: `aws_security_group.alb`
   - Resource: `aws_lb.main`

2. **Target Groups**
   - Backend API target group (port 8000)
     - Health check: `/api/v1/health`
     - Stickiness: Enabled for session persistence
     - Resource: `aws_lb_target_group.api`

   - Frontend target group (port 3000)
     - Health check: `/`
     - Resource: `aws_lb_target_group.frontend`

3. **Listeners**
   - HTTP listener (80): Redirect to HTTPS or forward to frontend
   - HTTPS listener (443): If `var.enable_https=true` with SSL cert
   - Resources: `aws_lb_listener.http`, `aws_lb_listener.https`

4. **Listener Rules**
   - Rule 1: `/api/*` paths → API target group
   - Rule 2: `/` → Frontend target group
   - Resources: `aws_lb_listener_rule.api`, `aws_lb_listener_rule.frontend`

**Health Check Configuration:**
```hcl
health_check {
  healthy_threshold   = var.health_check_healthy_threshold
  unhealthy_threshold = var.health_check_unhealthy_threshold
  timeout             = var.health_check_timeout
  interval            = var.health_check_interval
  path                = "/api/v1/health"
  matcher             = "200-399"
  port                = "traffic-port"
}
```

### Phase 5: ECS Cluster & Services (terraform/ecs.tf)

**File Path:** `terraform/ecs.tf` (400-500 lines) - **MOST COMPLEX**

**Components:**

1. **ECS Cluster**
   - Cluster name: `beast-{environment}-cluster`
   - Container Insights enabled: `var.container_insights_enabled`
   - Capacity providers: FARGATE, FARGATE_SPOT (for cost optimization)
   - Resource: `aws_ecs_cluster.main`

2. **CloudWatch Log Groups**
   - `/ecs/beast-{env}-api`
   - `/ecs/beast-{env}-frontend`
   - `/ecs/beast-{env}-celery-worker`
   - `/ecs/beast-{env}-celery-beat`
   - `/ecs/beast-{env}-postgres`
   - `/ecs/beast-{env}-mongodb`
   - `/ecs/beast-{env}-redis`
   - `/ecs/beast-{env}-ollama` (if enabled)
   - Resources: `aws_cloudwatch_log_group.*`

3. **Task Definition for Backend API**
   - CPU: `var.api_cpu` (512 default)
   - Memory: `var.api_memory` (1024 default)
   - Containers:
     - Container `beast-api` with FastAPI image
     - Port mappings and environment variables
   - Logging: CloudWatch Logs
   - Execution role: Task execution role
   - Task role: Application role for S3, Secrets Manager, etc.
   - Resource: `aws_ecs_task_definition.api`

4. **Task Definition for Frontend**
   - CPU: `var.frontend_cpu` (256)
   - Memory: `var.frontend_memory` (512)
   - Containers: Next.js frontend image
   - Port mappings: 3000
   - Resource: `aws_ecs_task_definition.frontend`

5. **Task Definition for Celery Worker**
   - Same CPU/memory as API
   - Container: API image with `celery -A app.celery worker`
   - Resource: `aws_ecs_task_definition.celery_worker`

6. **Task Definition for Celery Beat**
   - CPU: 256, Memory: 512
   - Container: API image with `celery -A app.celery beat`
   - Resource: `aws_ecs_task_definition.celery_beat`

7. **ECS Services**
   - **API Service**
     - Desired count: `var.api_desired_count`
     - Launch type: FARGATE
     - Network: Private subnets
     - Load balancer: Target group API
     - Auto-scaling: Based on CPU/memory
     - Resource: `aws_ecs_service.api`

   - **Frontend Service**
     - Desired count: `var.frontend_desired_count`
     - Launch type: FARGATE
     - Network: Private subnets
     - Load balancer: Target group frontend
     - Resource: `aws_ecs_service.frontend`

   - **Celery Worker Service**
     - Desired count: `var.celery_worker_desired_count`
     - No load balancer (internal service)
     - Resource: `aws_ecs_service.celery_worker`

   - **Celery Beat Service**
     - Desired count: 1 (scheduler runs on single node)
     - No load balancer
     - Resource: `aws_ecs_service.celery_beat`

8. **Auto Scaling Targets (if enabled)**
   - Target: ECS service CPU/memory utilization
   - Min capacity: `var.api_min_capacity`
   - Max capacity: `var.api_max_capacity`
   - Resources: `aws_appautoscaling_target.*`, `aws_appautoscaling_policy.*`

9. **Database Containers (Optional ECS Tasks)**
   - PostgreSQL: ECS task with volume mount for persistence
   - MongoDB: ECS task with volume mount
   - Redis: ECS task (optional)
   - Alternative: Use RDS/DocumentDB/ElastiCache (not included in this basic setup)

**Container Definition Example:**
```hcl
container_definitions = jsonencode([
  {
    name  = local.container_name_api
    image = "${aws_ecr_repository.backend.repository_url}:latest"
    portMappings = [
      {
        containerPort = var.api_port
        hostPort      = var.api_port
        protocol      = "tcp"
      }
    ]
    environment = [
      {
        name  = "ENVIRONMENT"
        value = var.environment
      },
      {
        name  = "API_HOST"
        value = "0.0.0.0"
      },
      {
        name  = "API_PORT"
        value = tostring(var.api_port)
      }
    ]
    secrets = [
      {
        name      = "DATABASE_URL"
        valueFrom = aws_secretsmanager_secret.db_postgres.arn
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "ecs"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.api_port}/health || exit 1"]
      interval    = var.health_check_interval
      timeout     = var.health_check_timeout
      retries     = var.health_check_unhealthy_threshold
      startPeriod = 60
    }
  }
])
```

### Phase 6: AWS Secrets Manager (terraform/secrets.tf)

**File Path:** `terraform/secrets.tf` (150-180 lines)

**Components:**

1. **Database Secrets**
   - PostgreSQL credentials: `beast/{env}/db/postgres`
   - MongoDB credentials: `beast/{env}/db/mongodb`
   - Redis password: `beast/{env}/cache/redis`

2. **Application Secrets**
   - JWT secret key: `beast/{env}/api/jwt`
   - OpenAI API key: `beast/{env}/providers/openai`
   - Gmail credentials: `beast/{env}/gmail`
   - Sentry DSN: `beast/{env}/sentry`

3. **Secret Versions**
   - Initial versions set during infrastructure creation
   - Manual update through AWS Console for sensitive values

**Resource:**
```hcl
resource "aws_secretsmanager_secret" "postgres_password" {
  name                    = "beast/${var.environment}/db/postgres"
  description             = "PostgreSQL password for Beast"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "postgres_password" {
  secret_id = aws_secretsmanager_secret.postgres_password.id
  secret_string = jsonencode({
    username = "beast"
    password = var.database_secrets["postgres_password"]
    hostname = aws_ecs_task_definition.postgres.id  # or RDS endpoint
    port     = var.postgres_port
    database = "beast"
  })
}
```

### Phase 7: Outputs (terraform/outputs.tf)

**File Path:** `terraform/outputs.tf` (100-120 lines)

**Key Outputs:**

1. **ALB DNS**
   - Output: ALB endpoint for API access
   - Usage: Update GitHub Actions workflows with ALB address

2. **ECR Repository URLs**
   - Backend image URI
   - Frontend image URI

3. **ECS Cluster Outputs**
   - Cluster ARN and name
   - Service names and ARNs

4. **CloudWatch Log Groups**
   - Log group names for monitoring

5. **VPC Details**
   - VPC ID
   - Subnet IDs
   - Security group IDs

**Example:**
```hcl
output "alb_dns_name" {
  description = "DNS name of ALB"
  value       = aws_lb.main.dns_name
}

output "backend_repository_url" {
  description = "ECR backend repository URL"
  value       = "${aws_ecr_repository.backend.repository_url}:latest"
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}
```

### Phase 8: Environment Files (terraform/environments/)

**Files:**
- `terraform/environments/dev.tfvars` (20-30 lines)
- `terraform/environments/staging.tfvars` (20-30 lines)
- `terraform/environments/prod.tfvars` (20-30 lines)

**Dev Environment Example:**
```hcl
environment            = "dev"
api_desired_count      = 1
frontend_desired_count = 1
api_cpu                = 256
api_memory             = 512
log_retention_days     = 7
enable_autoscaling     = false
```

**Staging Environment Example:**
```hcl
environment            = "staging"
api_desired_count      = 2
frontend_desired_count = 2
api_cpu                = 512
api_memory             = 1024
log_retention_days     = 14
enable_autoscaling     = true
```

**Production Environment Example:**
```hcl
environment                    = "production"
api_desired_count              = 3
frontend_desired_count         = 2
api_cpu                        = 1024
api_memory                     = 2048
enable_autoscaling             = true
enable_https                   = true
ssl_certificate_arn            = "arn:aws:acm:..."
container_insights_enabled     = true
health_check_unhealthy_threshold = 2
```

---

## 🔧 SETUP INSTRUCTIONS

### 1. Prerequisites
```bash
# Install Terraform
brew install terraform  # macOS
# or apt-get install terraform  # Linux

# Install AWS CLI
brew install awscli

# Configure AWS credentials
aws configure

# Verify access
aws sts get-caller-identity
```

### 2. Initialize Terraform
```bash
cd terraform
terraform init
```

### 3. Deploy Dev Environment
```bash
# Plan changes
terraform plan -var-file=environments/dev.tfvars

# Apply changes
terraform apply -var-file=environments/dev.tfvars

# Note outputs (ALB DNS, ECR URLs)
```

### 4. Setup GitHub OIDC (One-time)
```bash
# Get AWS Account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create OIDC provider (uses GitHub's OIDC endpoint)
aws iam create-openid-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list <get from GitHub documentation>

# Create role (created by terraform/iam.tf)
# Role ARN: arn:aws:iam::${AWS_ACCOUNT_ID}:role/github-actions-beast
```

### 5. Setup GitHub Actions Secrets
```bash
# In repository settings → Secrets and variables → Actions

# Required secrets:
AWS_ROLE_TO_ASSUME=arn:aws:iam::${AWS_ACCOUNT_ID}:role/github-actions-beast
AWS_REGION=us-east-1
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### 6. Deploy Staging then Production
```bash
# Staging
terraform plan -var-file=environments/staging.tfvars
terraform apply -var-file=environments/staging.tfvars

# Production
terraform plan -var-file=environments/prod.tfvars
terraform apply -var-file=environments/prod.tfvars
```

### 7. Verify Deployments
```bash
# Check ECS clusters
aws ecs list-clusters

# Check services
aws ecs list-services --cluster beast-dev-cluster

# Check task definitions
aws ecs list-task-definitions

# Check ECR repositories
aws ecr describe-repositories

# Check ALB
aws elbv2 describe-load-balancers

# Get ALB DNS
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[0].DNSName' \
  --output text
```

---

## 📋 CHECKLIST FOR NEXT SESSION

- [ ] Create `terraform/iam.tf` with roles and policies
- [ ] Create `terraform/ecr.tf` with backend/frontend repositories
- [ ] Create `terraform/alb.tf` with load balancer and target groups
- [ ] Create `terraform/ecs.tf` with cluster and services (MOST COMPLEX)
- [ ] Create `terraform/secrets.tf` with Secrets Manager setup
- [ ] Create `terraform/outputs.tf` with critical outputs
- [ ] Create `terraform/environments/dev.tfvars`
- [ ] Create `terraform/environments/staging.tfvars`
- [ ] Create `terraform/environments/prod.tfvars`
- [ ] Create `terraform/.gitignore` (exclude .tfstate, .terraform/)
- [ ] Update `backend/src/app/config.py` to read from AWS Secrets Manager
- [ ] Update `backend/pyproject.toml` to add boto3 dependency
- [ ] Create deployment documentation
- [ ] Test CI/CD pipeline end-to-end

---

## 🎯 NEXT STEPS

1. **Configure AWS Account**
   - Ensure sufficient IAM permissions
   - Create S3 bucket for Terraform state (optional but recommended)
   - Setup CloudFront for frontend distribution (optional)

2. **Create Remaining Terraform Files**
   - Follow the detailed specifications above
   - Test each component with `terraform plan` before applying
   - Use staging environment as testbed

3. **Update Application Code**
   - Backend: Read secrets from AWS Secrets Manager
   - Frontend: Build-time environment variables
   - Docker: Ensure healthchecks present

4. **Test CI/CD Pipeline**
   - Push to develop branch → Should trigger CI workflow
   - After CI passes → Should build and push to ECR
   - After push → Should deploy to dev environment
   - Manual deployment to prod with approvals

5. **Monitoring & Observability**
   - Setup CloudWatch dashboards
   - Configure alarms for high error rates
   - Setup log insights queries for troubleshooting
   - Monitor ALB metrics and target health

---

## 💾 STATE MANAGEMENT

**Initial Development:**
- Terraform state stored locally (`terraform.tfstate`)
- Not committed to Git (add to `.gitignore`)

**Production Best Practice:**
```bash
# After initial apply, setup remote state in S3
# Create S3 bucket
aws s3 mb s3://beast-terraform-state-${AWS_ACCOUNT_ID}

# Create DynamoDB table for locks
aws dynamodb create-table \
  --table-name beast-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# Uncomment backend configuration in terraform/main.tf
# Then run: terraform init (to migrate state to S3)
```

---

## 📞 TROUBLESHOOTING

**Task Won't Start**
- Check CloudWatch logs: `/ecs/beast-{env}-api`
- Verify image exists in ECR: `aws ecr describe-images --repository-name beast-backend`
- Check task definition: `aws ecs describe-task-definition --task-definition beast-api-{env}`
- Verify IAM role has permissions

**ALB Returns 502 Bad Gateway**
- Check target health: `aws elbv2 describe-target-health --target-group-arn arn:...`
- Verify security groups allow traffic: Port 8000 (API), 3000 (frontend)
- Check healthcheck path: `/api/v1/health` for API

**Deployment Hangs**
- Check if previous deployment still rolling: `aws ecs describe-services --cluster beast-dev-cluster --services beast-api`
- Force new deployment: `aws ecs update-service --cluster ... --service ... --force-new-deployment`

**ECR Push Fails**
- Verify AWS credentials: `aws sts get-caller-identity`
- Check ECR repository exists: `aws ecr describe-repositories`
- Verify IAM has `ecr:GetAuthorizationToken`: `aws ecr get-authorization-token`

---

*This guide provides the complete specification for implementing the CI/CD pipeline to AWS ECS. Each section includes the file path, line count, and detailed implementation guide.*
