# ============================================================================
# Application Load Balancer Configuration
# ============================================================================

# ==============================================================================
# ALB (Application Load Balancer)
# ==============================================================================

resource "aws_lb" "main" {
  name               = "${local.alb_name}-alb"
  internal           = var.alb_internal
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = var.environment == "production" ? true : false
  enable_http2               = true
  enable_cross_zone_load_balancing = true

  tags = {
    Name = "${local.alb_name}-alb"
  }
}

# ==============================================================================
# Target Groups
# ==============================================================================

# Backend API Target Group
resource "aws_lb_target_group" "api" {
  name        = local.tg_api_name
  port        = var.api_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    healthy_threshold   = var.health_check_healthy_threshold
    unhealthy_threshold = var.health_check_unhealthy_threshold
    timeout             = var.health_check_timeout
    interval            = var.health_check_interval
    path                = var.api_health_check_path
    matcher             = "200-399"
    port                = "traffic-port"
  }

  deregistration_delay = 30

  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  tags = {
    Name = local.tg_api_name
  }

  depends_on = [aws_lb.main]
}

# Frontend Target Group
resource "aws_lb_target_group" "frontend" {
  name        = local.tg_frontend_name
  port        = var.frontend_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    healthy_threshold   = var.health_check_healthy_threshold
    unhealthy_threshold = var.health_check_unhealthy_threshold
    timeout             = var.health_check_timeout
    interval            = var.health_check_interval
    path                = var.frontend_health_check_path
    matcher             = "200-399"
    port                = "traffic-port"
  }

  deregistration_delay = 30

  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400
    enabled         = true
  }

  tags = {
    Name = local.tg_frontend_name
  }

  depends_on = [aws_lb.main]
}

# ==============================================================================
# HTTP Listener (Port 80)
# ==============================================================================

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "forward"
    forward {
      target_group {
        arn    = aws_lb_target_group.frontend.arn
        weight = 100
      }
    }
  }

  tags = {
    Name = "${local.alb_name}-http-listener"
  }
}

# ==============================================================================
# HTTPS Listener (Port 443) - Optional
# ==============================================================================

resource "aws_lb_listener" "https" {
  count = var.enable_https ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.ssl_certificate_arn

  default_action {
    type = "forward"
    forward {
      target_group {
        arn    = aws_lb_target_group.frontend.arn
        weight = 100
      }
    }
  }

  tags = {
    Name = "${local.alb_name}-https-listener"
  }
}

# ==============================================================================
# Listener Rules
# ==============================================================================

# Rule 1: Route /api/* to backend target group (HTTP)
resource "aws_lb_listener_rule" "api_http" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }

  tags = {
    Name = "${local.alb_name}-api-rule"
  }
}

# Rule 2: Route /api/* to backend target group (HTTPS if enabled)
resource "aws_lb_listener_rule" "api_https" {
  count = var.enable_https ? 1 : 0

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 1

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }

  tags = {
    Name = "${local.alb_name}-api-rule-https"
  }
}

# ==============================================================================
# Security Group for ALB (already defined in vpc.tf but referenced here)
# ==============================================================================

# Output reference to the ALB security group from vpc.tf

# ==============================================================================
# CloudWatch Alarms for ALB
# ==============================================================================

resource "aws_cloudwatch_metric_alarm" "alb_target_health" {
  alarm_name          = "${local.alb_name}-unhealthy-targets"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "0"
  alarm_description   = "Alert when there are unhealthy targets in the load balancer"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }

  tags = {
    Name = "${local.alb_name}-unhealthy-targets"
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_response_time" {
  alarm_name          = "${local.alb_name}-high-response-time"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "Alert when response time is high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }

  tags = {
    Name = "${local.alb_name}-high-response-time"
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_http_5xx_errors" {
  alarm_name          = "${local.alb_name}-high-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "Alert when there are many 5XX errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
  }

  tags = {
    Name = "${local.alb_name}-high-5xx-errors"
  }
}

# ==============================================================================
# Outputs
# ==============================================================================

output "alb_arn" {
  description = "ARN of the load balancer"
  value       = aws_lb.main.arn
}

output "alb_dns_name" {
  description = "DNS name of the load balancer"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the load balancer"
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
