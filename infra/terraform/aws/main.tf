data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

locals {
  name = "${var.project_name}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = local.name }
}

resource "aws_subnet" "private" {
  for_each = { for index, az in local.azs : az => index }

  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, each.value)
  tags              = { Name = "${local.name}-private-${each.value + 1}" }
}

resource "aws_security_group" "database" {
  name        = "${local.name}-database"
  description = "PostgreSQL access from the FlowPilot workload security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from application workloads"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.workloads.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "workloads" {
  name        = "${local.name}-workloads"
  description = "Security group assigned to FlowPilot workloads"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = values(aws_subnet.private)[*].id
}

resource "aws_db_instance" "postgres" {
  identifier                     = local.name
  engine                         = "postgres"
  engine_version                 = "17"
  instance_class                 = var.database_instance_class
  allocated_storage              = var.database_allocated_storage_gb
  max_allocated_storage          = max(100, var.database_allocated_storage_gb)
  storage_type                   = "gp3"
  storage_encrypted              = true
  db_name                        = var.database_name
  username                       = var.database_username
  manage_master_user_password    = true
  db_subnet_group_name           = aws_db_subnet_group.main.name
  vpc_security_group_ids         = [aws_security_group.database.id]
  multi_az                       = var.database_multi_az
  publicly_accessible            = false
  backup_retention_period        = var.environment == "production" ? 14 : 3
  deletion_protection            = var.environment == "production"
  skip_final_snapshot            = var.environment != "production"
  performance_insights_enabled   = true
  auto_minor_version_upgrade     = true
  apply_immediately              = var.environment != "production"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}

resource "aws_ecr_repository" "images" {
  for_each = toset(["api", "worker", "web", "odoo-mcp"])

  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_s3_bucket" "artifacts" {
  bucket_prefix = "${local.name}-artifacts-"
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name}-dead-letter"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${local.name}-jobs"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 6
  })
}

resource "aws_secretsmanager_secret" "application" {
  name                    = "${local.name}/application"
  recovery_window_in_days = var.environment == "production" ? 30 : 0
  description             = "OpenAI, Odoo, OIDC, and action-signing secrets for FlowPilot"
}

resource "aws_cloudwatch_log_group" "application" {
  name              = "/flowpilot/${var.environment}/application"
  retention_in_days = var.environment == "production" ? 90 : 14
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = var.budget_notification_email == "" ? [] : [var.budget_notification_email]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = 80
      threshold_type             = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = [notification.value]
    }
  }
}
