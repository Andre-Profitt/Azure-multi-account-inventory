# Enhanced Features Documentation

## Overview

This document details all the enhanced features added to the AWS Multi-Account Inventory system, including cost analysis, security monitoring, and advanced querying capabilities.

## Table of Contents

1. [Enhanced Resource Collection](#enhanced-resource-collection)
2. [Cost Analysis & Optimization](#cost-analysis--optimization)
3. [Security Compliance](#security-compliance)
4. [Advanced Query Tool](#advanced-query-tool)
5. [Automated Reporting](#automated-reporting)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Lambda Function Actions](#lambda-function-actions)

## Enhanced Resource Collection

### Supported Resource Types

#### EC2 Instances
- **Collected Attributes**:
  - Instance type, state, launch time
  - Network configuration (VPC, subnet, security groups)
  - Public/private IP addresses
  - IAM instance profile
  - All tags
- **Cost Estimation**: Based on instance type and running state
- **Optimization Checks**: Idle instances, oversized instances

#### RDS Databases
- **Collected Attributes**:
  - Engine type and version
  - Instance class and status
  - Storage size and encryption status
  - Multi-AZ configuration
  - Backup retention period
- **Cost Estimation**: Based on instance class and availability
- **Security Checks**: Unencrypted storage

#### S3 Buckets
- **Collected Attributes**:
  - Bucket size (from CloudWatch metrics)
  - Versioning status
  - Encryption configuration
  - Public access status
  - Storage class
- **Cost Estimation**: Based on storage size and class
- **Security Checks**: Unencrypted buckets, public access

#### Lambda Functions
- **Collected Attributes**:
  - Runtime and memory configuration
  - Monthly invocation count
  - Error rate
  - Code size and timeout
- **Cost Estimation**: Based on invocations and GB-seconds
- **Optimization Checks**: Unused functions, high error rates

### Parallel Collection

The enhanced collector uses ThreadPoolExecutor for parallel region and resource type collection, significantly improving performance for large deployments.

## Cost Analysis & Optimization

### Real-time Cost Estimation

Each resource is assigned an estimated monthly cost based on:
- Current AWS pricing (simplified model)
- Resource configuration and state
- Usage metrics where available

### Cost Analysis Features

```bash
# Run comprehensive cost analysis
python -m src.query.enhanced_inventory_query --action cost
```

**Output includes**:
1. Total monthly cost and yearly projection
2. Top 20 most expensive resources
3. Cost breakdown by:
   - Resource type
   - AWS account
   - Region
   - Department (via tags)

### Optimization Recommendations

The system automatically identifies:

#### Idle Resources
- EC2 instances stopped for >30 days
- Lambda functions with <10 invocations/month
- Empty S3 buckets older than 90 days

#### Oversized Resources
- Large EC2 instance types (m5.2xlarge and above)
- Potential savings estimated at 30% for downsizing

#### Example Output
```
=== Cost Analysis Report ===
Total Monthly Cost: $45,678.32
Yearly Projection: $548,139.84
Potential Monthly Savings: $8,234.56

--- Idle Resources (23) ---
• EC2 Instance - i-1234567890abcdef0
  Reason: Stopped for 45 days
  Recommendation: Consider terminating or creating an AMI
  Potential Savings: $0.00/month

• Lambda Function - data-processor
  Reason: Only 5 invocations/month
  Recommendation: Consider removing unused function
  Potential Savings: $12.34/month
```

## Security Compliance

### Automated Security Checks

Weekly security scans identify:

1. **Unencrypted Resources**:
   - RDS instances without storage encryption
   - S3 buckets without default encryption
   - EBS volumes without encryption (when added)

2. **Public Access Risks**:
   - S3 buckets with public access enabled
   - RDS instances with public endpoints (when added)
   - Security groups with 0.0.0.0/0 rules (when added)

### Security Query

```bash
# Run security analysis
python -m src.query.enhanced_inventory_query --action security
```

### Compliance Alerts

Automated SNS notifications for:
- New unencrypted resources
- Public access changes
- Failed security checks

## Advanced Query Tool

### Filtering Options

```bash
# Filter by multiple criteria
python -m src.query.enhanced_inventory_query \
  --action export \
  --account-name production \
  --resource-type ec2_instance \
  --region us-east-1 \
  --department engineering \
  --days 7 \
  --output recent-engineering-ec2.csv
```

### Export Formats

1. **CSV Export**:
   - Flattened data structure
   - Includes key attributes per resource type
   - Tag-based filtering (Department, Environment, Owner)

2. **JSON Export**:
   - Complete resource data
   - Nested attributes preserved
   - Suitable for programmatic processing

### Stale Resource Detection

```bash
# Find resources unused for 90+ days
python -m src.query.enhanced_inventory_query --action stale --days 90
```

Identifies:
- Stopped EC2 instances
- Unused Lambda functions
- Empty S3 buckets
- Zero-traffic load balancers (when added)

## Automated Reporting

### Report Types

1. **Daily Cost Report** (9 AM UTC):
   - Total costs and trends
   - Top expensive resources
   - New resources added
   - Cost anomalies

2. **Weekly Security Report** (Mondays):
   - Security compliance summary
   - New vulnerabilities
   - Remediation progress

3. **Monthly Optimization Report** (1st of month):
   - Stale resource summary
   - Savings opportunities
   - Usage trends

### Report Storage

All reports are automatically saved to S3:
```
s3://[stack-name]-reports-[account-id]/
├── cost-reports/
│   └── 2024/01/15/cost-analysis.json
├── security-reports/
│   └── 2024/01/15/security-summary.json
└── cleanup-reports/
    └── 2024/01/01/stale-resources.json
```

## Monitoring & Alerts

### CloudWatch Dashboard

Real-time metrics including:
- Resources collected per run
- Collection duration
- Total monthly cost
- Error rates
- Security issues count

### CloudWatch Alarms

1. **High Cost Alarm**:
   - Threshold: $10,000/month (configurable)
   - Action: SNS notification

2. **Collection Error Alarm**:
   - Threshold: 5 errors in 1 hour
   - Action: SNS notification

3. **Lambda Error Alarm**:
   - Threshold: 5 errors in 5 minutes
   - Action: SNS notification

### Custom Metrics

The system publishes custom CloudWatch metrics:
- `AWSInventory/ResourcesCollected`
- `AWSInventory/CollectionDuration`
- `AWSInventory/TotalMonthlyCost`
- `AWSInventory/PotentialSavings`
- `AWSInventory/SecurityIssues`

## Lambda Function Actions

The enhanced Lambda handler supports multiple actions:

### 1. Collect (Default)
```json
{
  "action": "collect",
  "accounts": {
    "production": {
      "account_id": "123456789012",
      "role_name": "InventoryRole"
    }
  }
}
```

### 2. Cost Analysis
```json
{
  "action": "analyze_cost",
  "send_report": true
}
```

### 3. Security Check
```json
{
  "action": "check_security"
}
```

### 4. Stale Cleanup Check
```json
{
  "action": "cleanup_stale",
  "days": 90
}
```

## Configuration

### Enhanced Account Configuration

```json
{
  "accounts": {
    "production": {
      "account_id": "123456789012",
      "role_name": "InventoryRole",
      "tags": {
        "Environment": "Production",
        "CostCenter": "Engineering"
      }
    }
  },
  "collection_settings": {
    "regions": ["us-east-1", "us-west-2"],
    "resource_types": ["ec2_instance", "rds_instance", "s3_bucket", "lambda_function"],
    "cost_thresholds": {
      "monthly_alert": 10000,
      "resource_alert": 500
    }
  },
  "notification_settings": {
    "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:inventory-alerts",
    "alert_types": ["cost_threshold", "security_issues", "collection_errors"]
  }
}
```

## Testing

### Unit Tests

Comprehensive test coverage for:
- Resource collectors (mocked AWS APIs)
- Cost estimation logic
- Query functionality
- Lambda handlers

Run tests:
```bash
python -m pytest tests/unit/test_enhanced_collector.py -v
```

### Integration Testing

Test the complete system:
```bash
# Test Lambda locally
python -m src.lambda.enhanced_handler

# Test with sample event
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload file://tests/events/collect-event.json \
  output.json
```

## Performance Considerations

1. **Parallel Processing**:
   - 10 concurrent threads for region collection
   - 5 concurrent threads for account processing

2. **DynamoDB Optimization**:
   - Batch writes (25 items per batch)
   - On-demand billing for variable workloads

3. **Lambda Configuration**:
   - 1GB memory for optimal performance
   - 5-minute timeout for large deployments
   - Reserved concurrency to prevent throttling

## Troubleshooting

### Common Issues

1. **High Lambda Costs**:
   - Check invocation frequency
   - Verify memory allocation
   - Review CloudWatch logs for errors

2. **Missing Resources**:
   - Verify IAM permissions
   - Check region coverage
   - Review CloudWatch logs

3. **Cost Estimation Inaccuracy**:
   - Update pricing in `cost_estimates` dict
   - Add resource-specific pricing logic
   - Consider using AWS Pricing API

### Debug Mode

Enable debug logging via the ``LOG_LEVEL`` environment variable (default ``INFO``):
```python
# In Lambda environment variable
LOG_LEVEL=DEBUG

# For local testing
python src/collector/enhanced_main.py --debug
```