terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    # Configure your backend settings
    # bucket = "your-terraform-state-bucket"
    # key    = "aws-inventory/terraform.tfstate"
    # region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# DynamoDB Table with enhanced schema
resource "aws_dynamodb_table" "inventory" {
  name           = var.dynamodb_table_name
  billing_mode   = var.dynamodb_billing_mode
  read_capacity  = var.dynamodb_billing_mode == "PROVISIONED" ? var.dynamodb_read_capacity : null
  write_capacity = var.dynamodb_billing_mode == "PROVISIONED" ? var.dynamodb_write_capacity : null
  
  hash_key  = "pk"
  range_key = "sk"
  
  attribute {
    name = "pk"
    type = "S"
  }
  
  attribute {
    name = "sk"
    type = "S"
  }
  
  attribute {
    name = "resource_type"
    type = "S"
  }
  
  attribute {
    name = "department"
    type = "S"
  }
  
  attribute {
    name = "account_id"
    type = "S"
  }
  
  attribute {
    name = "timestamp"
    type = "S"
  }
  
  # Indexes for efficient querying
  global_secondary_index {
    name            = "resource-type-index"
    hash_key        = "resource_type"
    range_key       = "sk"
    write_capacity  = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    read_capacity   = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    projection_type = "ALL"
  }
  
  global_secondary_index {
    name            = "department-index"
    hash_key        = "department"
    range_key       = "sk"
    write_capacity  = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    read_capacity   = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    projection_type = "ALL"
  }
  
  global_secondary_index {
    name            = "account-timestamp-index"
    hash_key        = "account_id"
    range_key       = "timestamp"
    write_capacity  = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    read_capacity   = var.dynamodb_billing_mode == "PROVISIONED" ? 5 : null
    projection_type = "ALL"
  }
  
  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }
  
  # Server-side encryption
  server_side_encryption {
    enabled = true
  }
  
  tags = {
    Name        = "AWS Inventory Table"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# S3 bucket for Lambda deployment packages
resource "aws_s3_bucket" "lambda_deployment" {
  bucket = "${var.stack_name}-deployment-${data.aws_caller_identity.current.account_id}"
  
  tags = {
    Name        = "Lambda Deployment Bucket"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# S3 bucket versioning
resource "aws_s3_bucket_versioning" "lambda_deployment" {
  bucket = aws_s3_bucket.lambda_deployment.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 bucket for reports
resource "aws_s3_bucket" "reports" {
  bucket = "${var.stack_name}-reports-${data.aws_caller_identity.current.account_id}"
  
  tags = {
    Name        = "Inventory Reports"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# S3 bucket lifecycle for reports
resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  
  rule {
    id     = "delete-old-reports"
    status = "Enabled"
    
    expiration {
      days = 90
    }
    
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
  
  rule {
    id     = "transition-old-reports"
    status = "Enabled"
    
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    
    transition {
      days          = 60
      storage_class = "GLACIER"
    }
  }
}

# SNS Topic for alerts
resource "aws_sns_topic" "alerts" {
  name         = "${var.stack_name}-alerts"
  display_name = "AWS Inventory Alerts"
  
  tags = {
    Name        = "Inventory Alerts"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# SNS Topic subscription
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# Lambda Execution Role with enhanced permissions
resource "aws_iam_role" "lambda_execution" {
  name = "${var.stack_name}-lambda-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Name        = "Lambda Execution Role"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# Lambda Execution Role Policy
resource "aws_iam_role_policy" "lambda_execution_policy" {
  name = "${var.stack_name}-lambda-policy"
  role = aws_iam_role.lambda_execution.id
  
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
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.inventory.arn,
          "${aws_dynamodb_table.inventory.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sts:AssumeRole"
        ]
        Resource = "arn:aws:iam::*:role/InventoryRole"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeRegions"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.reports.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.alerts.arn
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "AWSInventory"
          }
        }
      }
    ]
  })
}

# Lambda basic execution policy attachment
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda Layer for dependencies
resource "aws_lambda_layer_version" "dependencies" {
  layer_name          = "${var.stack_name}-dependencies"
  filename            = "../lambda-layer.zip"
  compatible_runtimes = ["python3.9", "python3.10", "python3.11"]
  description         = "Dependencies for AWS inventory collector"
  
  lifecycle {
    ignore_changes = [filename]
  }
}

# Main Lambda Function
resource "aws_lambda_function" "inventory_collector" {
  function_name = "${var.stack_name}-collector"
  role          = aws_iam_role.lambda_execution.arn
  
  filename         = "../lambda-deployment.zip"
  source_code_hash = filebase64sha256("../lambda-deployment.zip")
  
  handler = "handler.lambda_handler"
  runtime = "python3.9"
  timeout = var.lambda_timeout
  memory_size = var.lambda_memory
  
  layers = [aws_lambda_layer_version.dependencies.arn]
  
  reserved_concurrent_executions = 10
  
  environment {
    variables = {
      DYNAMODB_TABLE_NAME  = aws_dynamodb_table.inventory.name
      SNS_TOPIC_ARN       = aws_sns_topic.alerts.arn
      COST_ALERT_THRESHOLD = var.cost_alert_threshold
      REPORTS_S3_BUCKET   = aws_s3_bucket.reports.id
      ENVIRONMENT         = var.environment
      LOG_LEVEL           = var.log_level
    }
  }
  
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
  
  tags = {
    Name        = "Inventory Collector Lambda"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.inventory_collector.function_name}"
  retention_in_days = var.log_retention_days
  
  tags = {
    Name        = "Lambda Logs"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# EventBridge Rules for different schedules
resource "aws_cloudwatch_event_rule" "inventory_schedule" {
  name                = "${var.stack_name}-collection-schedule"
  description         = "Trigger inventory collection"
  schedule_expression = var.schedule_expression
  
  tags = {
    Name        = "Inventory Collection Schedule"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

resource "aws_cloudwatch_event_rule" "daily_cost_analysis" {
  name                = "${var.stack_name}-daily-cost-analysis"
  description         = "Daily cost analysis and report"
  schedule_expression = "cron(0 9 * * ? *)"
  
  tags = {
    Name        = "Daily Cost Analysis"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

resource "aws_cloudwatch_event_rule" "weekly_security_check" {
  name                = "${var.stack_name}-weekly-security"
  description         = "Weekly security compliance check"
  schedule_expression = "cron(0 9 ? * MON *)"
  
  tags = {
    Name        = "Weekly Security Check"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

resource "aws_cloudwatch_event_rule" "monthly_cleanup" {
  name                = "${var.stack_name}-monthly-cleanup"
  description         = "Monthly stale resource check"
  schedule_expression = "cron(0 9 1 * ? *)"
  
  tags = {
    Name        = "Monthly Cleanup Check"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# EventBridge Targets
resource "aws_cloudwatch_event_target" "collection_target" {
  rule      = aws_cloudwatch_event_rule.inventory_schedule.name
  target_id = "CollectionTarget"
  arn       = aws_lambda_function.inventory_collector.arn
  input     = jsonencode({ action = "collect" })
}

resource "aws_cloudwatch_event_target" "cost_target" {
  rule      = aws_cloudwatch_event_rule.daily_cost_analysis.name
  target_id = "CostAnalysisTarget"
  arn       = aws_lambda_function.inventory_collector.arn
  input     = jsonencode({ action = "analyze_cost", send_report = true })
}

resource "aws_cloudwatch_event_target" "security_target" {
  rule      = aws_cloudwatch_event_rule.weekly_security_check.name
  target_id = "SecurityCheckTarget"
  arn       = aws_lambda_function.inventory_collector.arn
  input     = jsonencode({ action = "check_security" })
}

resource "aws_cloudwatch_event_target" "cleanup_target" {
  rule      = aws_cloudwatch_event_rule.monthly_cleanup.name
  target_id = "CleanupTarget"
  arn       = aws_lambda_function.inventory_collector.arn
  input     = jsonencode({ action = "cleanup_stale", days = 90 })
}

# Lambda Permissions for EventBridge
resource "aws_lambda_permission" "allow_collection" {
  statement_id  = "AllowCollectionSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inventory_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.inventory_schedule.arn
}

resource "aws_lambda_permission" "allow_cost" {
  statement_id  = "AllowCostAnalysis"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inventory_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_cost_analysis.arn
}

resource "aws_lambda_permission" "allow_security" {
  statement_id  = "AllowSecurityCheck"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inventory_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_security_check.arn
}

resource "aws_lambda_permission" "allow_cleanup" {
  statement_id  = "AllowCleanupCheck"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inventory_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.monthly_cleanup.arn
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "high_cost" {
  count = var.enable_monitoring ? 1 : 0
  
  alarm_name          = "${var.stack_name}-high-cost"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "TotalMonthlyCost"
  namespace           = "AWSInventory"
  period              = "3600"
  statistic           = "Maximum"
  threshold           = var.cost_alert_threshold
  alarm_description   = "Alert when total monthly cost exceeds threshold"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
  
  tags = {
    Name        = "High Cost Alarm"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

resource "aws_cloudwatch_metric_alarm" "collection_errors" {
  count = var.enable_monitoring ? 1 : 0
  
  alarm_name          = "${var.stack_name}-collection-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CollectionErrors"
  namespace           = "AWSInventory"
  period              = "3600"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Alert on collection errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
  
  tags = {
    Name        = "Collection Errors Alarm"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count = var.enable_monitoring ? 1 : 0
  
  alarm_name          = "${var.stack_name}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Alert on Lambda function errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    FunctionName = aws_lambda_function.inventory_collector.function_name
  }
  
  tags = {
    Name        = "Lambda Errors Alarm"
    Environment = var.environment
    Project     = "aws-multi-account-inventory"
  }
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "inventory" {
  count = var.enable_monitoring ? 1 : 0
  
  dashboard_name = "${var.stack_name}-inventory"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWSInventory", "ResourcesCollected", { stat = "Sum" }],
            [".", "CollectionDuration", { stat = "Average", yAxis = "right" }]
          ]
          period = 3600
          stat   = "Average"
          region = var.aws_region
          title  = "Collection Metrics"
          yAxis = {
            left  = { label = "Resources" }
            right = { label = "Duration (seconds)" }
          }
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWSInventory", "TotalMonthlyCost", { stat = "Maximum" }],
            [".", "PotentialSavings", { stat = "Maximum" }]
          ]
          period = 86400
          stat   = "Maximum"
          region = var.aws_region
          title  = "Cost Metrics"
          yAxis = {
            left = { label = "USD" }
          }
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWSInventory", "UnencryptedResources", { stat = "Maximum" }],
            [".", "PublicResources", { stat = "Maximum" }],
            [".", "IdleResources", { stat = "Maximum" }]
          ]
          period = 86400
          stat   = "Maximum"
          region = var.aws_region
          title  = "Security & Optimization"
        }
      },
      {
        type   = "log"
        width  = 12
        height = 6
        properties = {
          query   = "SOURCE '${aws_cloudwatch_log_group.lambda_logs.name}' | fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit 20"
          region  = var.aws_region
          title   = "Recent Errors"
          queryType = "Logs"
        }
      }
    ]
  })
}