variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "stack_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "aws-inventory"
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  type        = string
  default     = "aws-inventory"
}

variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode (PROVISIONED or PAY_PER_REQUEST)"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "dynamodb_read_capacity" {
  description = "DynamoDB read capacity units (only for PROVISIONED mode)"
  type        = number
  default     = 10
}

variable "dynamodb_write_capacity" {
  description = "DynamoDB write capacity units (only for PROVISIONED mode)"
  type        = number
  default     = 10
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 1024
}

variable "schedule_expression" {
  description = "EventBridge schedule expression for inventory collection"
  type        = string
  default     = "rate(6 hours)"
}

variable "notification_email" {
  description = "Email address for alerts and reports"
  type        = string
}

variable "cost_alert_threshold" {
  description = "Monthly cost threshold for alerts (USD)"
  type        = number
  default     = 10000
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "enable_monitoring" {
  description = "Enable CloudWatch dashboard and alarms"
  type        = bool
  default     = true
}

variable "external_id" {
  description = "External ID for cross-account role assumption"
  type        = string
  default     = "inventory-collector"
}

variable "log_level" {
  description = "Logging level for the Lambda function"
  type        = string
  default     = "INFO"
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}