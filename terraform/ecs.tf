# ============================================================================
# ECS Cluster and Services Configuration
# ============================================================================

# ==============================================================================
# ECS Cluster
# ==============================================================================

resource "aws_ecs_cluster" "main" {
  name = local.cluster_name

  setting {
    name  = "containerInsights"
    value = var.container_insights_enabled ? "enabled" : "disabled"
  }

  tags = {
    Name = local.cluster_name
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }

  default_capacity_provider_strategy {
    weight            = var.environment != "production" ? 100 : 0
    capacity_provider = "FARGATE_SPOT"
  }
}

# ==============================================================================
# CloudWatch Log Groups
# ==============================================================================

resource "aws_cloudwatch_log_group" "ecs_api" {
  name              = "/ecs/${local.service_prefix}-api"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.service_prefix}-api-logs"
  }
}

resource "aws_cloudwatch_log_group" "ecs_frontend" {
  name              = "/ecs/${local.service_prefix}-frontend"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.service_prefix}-frontend-logs"
  }
}

resource "aws_cloudwatch_log_group" "ecs_celery_worker" {
  name              = "/ecs/${local.service_prefix}-celery-worker"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.service_prefix}-celery-worker-logs"
  }
}

resource "aws_cloudwatch_log_group" "ecs_celery_beat" {
  name              = "/ecs/${local.service_prefix}-celery-beat"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.service_prefix}-celery-beat-logs"
  }
}

# ==============================================================================
# Task Definition: Backend API
# ==============================================================================

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.service_prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name_api
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true

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

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_api.name
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

  tags = {
    Name = "${local.service_prefix}-api-task-definition"
  }
}

# ==============================================================================
# Task Definition: Frontend
# ==============================================================================

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.service_prefix}-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.frontend_cpu
  memory                   = var.frontend_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name_frontend
      image     = "${aws_ecr_repository.frontend.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = var.frontend_port
          hostPort      = var.frontend_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_frontend.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.frontend_port}/ || exit 1"]
        interval    = var.health_check_interval
        timeout     = var.health_check_timeout
        retries     = var.health_check_unhealthy_threshold
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "${local.service_prefix}-frontend-task-definition"
  }
}

# ==============================================================================
# Task Definition: Celery Worker
# ==============================================================================

resource "aws_ecs_task_definition" "celery_worker" {
  family                   = "${local.service_prefix}-celery-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.celery_worker_cpu
  memory                   = var.celery_worker_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name_worker
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true

      command = [
        "celery",
        "-A", "app.celery",
        "worker",
        "--loglevel=info",
        "--concurrency=4"
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_celery_worker.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = {
    Name = "${local.service_prefix}-celery-worker-task-definition"
  }
}

# ==============================================================================
# Task Definition: Celery Beat
# ==============================================================================

resource "aws_ecs_task_definition" "celery_beat" {
  family                   = "${local.service_prefix}-celery-beat"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.celery_beat_cpu
  memory                   = var.celery_beat_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = local.container_name_beat
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true

      command = [
        "celery",
        "-A", "app.celery",
        "beat",
        "--loglevel=info",
        "--scheduler=redbeat.RedBeatScheduler"
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_celery_beat.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = {
    Name = "${local.service_prefix}-celery-beat-task-definition"
  }
}

# ==============================================================================
# ECS Services
# ==============================================================================

# Backend API Service
resource "aws_ecs_service" "api" {
  name            = "${local.service_prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = local.container_name_api
    container_port   = var.api_port
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy.ecs_task_execution_secrets_policy
  ]

  tags = {
    Name = "${local.service_prefix}-api-service"
  }
}

# Frontend Service
resource "aws_ecs_service" "frontend" {
  name            = "${local.service_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = var.frontend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = local.container_name_frontend
    container_port   = var.frontend_port
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy.ecs_task_execution_secrets_policy
  ]

  tags = {
    Name = "${local.service_prefix}-frontend-service"
  }
}

# Celery Worker Service
resource "aws_ecs_service" "celery_worker" {
  name            = "${local.service_prefix}-celery-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.celery_worker.arn
  desired_count   = var.celery_worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  depends_on = [aws_iam_role_policy.ecs_task_execution_secrets_policy]

  tags = {
    Name = "${local.service_prefix}-celery-worker-service"
  }
}

# Celery Beat Service
resource "aws_ecs_service" "celery_beat" {
  name            = "${local.service_prefix}-celery-beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.celery_beat.arn
  desired_count   = var.celery_beat_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  depends_on = [aws_iam_role_policy.ecs_task_execution_secrets_policy]

  tags = {
    Name = "${local.service_prefix}-celery-beat-service"
  }
}

# ==============================================================================
# Auto Scaling Target and Policies (if enabled)
# ==============================================================================

resource "aws_appautoscaling_target" "api_target" {
  count = var.enable_autoscaling ? 1 : 0

  max_capacity       = var.api_max_capacity
  min_capacity       = var.api_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu_scaling" {
  count = var.enable_autoscaling ? 1 : 0

  policy_name       = "${local.service_prefix}-api-cpu-scaling"
  policy_type       = "TargetTrackingScaling"
  resource_id       = aws_appautoscaling_target.api_target[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api_target[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.api_target[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.api_cpu_target_utilization
  }
}

resource "aws_appautoscaling_policy" "api_memory_scaling" {
  count = var.enable_autoscaling ? 1 : 0

  policy_name        = "${local.service_prefix}-api-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api_target[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api_target[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.api_target[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value = var.api_memory_target_utilization
  }
}

# ==============================================================================
# CloudWatch Alarms for ECS Services
# ==============================================================================

resource "aws_cloudwatch_metric_alarm" "api_cpu_high" {
  alarm_name          = "${local.service_prefix}-api-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "Alert when API CPU is high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.api.name
  }

  tags = {
    Name = "${local.service_prefix}-api-cpu-high"
  }
}

resource "aws_cloudwatch_metric_alarm" "api_memory_high" {
  alarm_name          = "${local.service_prefix}-api-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = "60"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "Alert when API memory is high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.api.name
  }

  tags = {
    Name = "${local.service_prefix}-api-memory-high"
  }
}

# ==============================================================================
# Outputs
# ==============================================================================

output "ecs_cluster_id" {
  description = "ID of ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_name" {
  description = "Name of ECS cluster"
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

output "frontend_service_name" {
  description = "Name of frontend ECS service"
  value       = aws_ecs_service.frontend.name
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

output "frontend_task_definition_arn" {
  description = "ARN of frontend task definition"
  value       = aws_ecs_task_definition.frontend.arn
}
