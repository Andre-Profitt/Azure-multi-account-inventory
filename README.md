# AWS Multi-Account Inventory System

A comprehensive serverless solution for collecting, analyzing, and optimizing AWS resource inventory across multiple accounts with advanced cost analysis and security compliance features.

## Overview

This enhanced system automatically discovers and catalogs AWS resources across multiple accounts, performs cost analysis, identifies optimization opportunities, and monitors security compliance. All data is stored in a centralized DynamoDB table with Global Secondary Indexes for efficient querying.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│   EventBridge   │────▶│    Lambda    │────▶│   DynamoDB    │────▶│ CloudWatch   │
│  (Scheduled)    │     │   Function   │     │  Table + GSI  │     │   Metrics    │
└─────────────────┘     └──────┬───────┘     └───────────────┘     └──────────────┘
                               │                                             │
                               │ Assumes Role                               ▼
                               ▼                                    ┌──────────────┐
                      ┌─────────────────┐                          │     SNS      │
                      │  Target Account │                          │   Topics     │
                      │  InventoryRole  │                          └──────────────┘
                      └─────────────────┘                                   │
                                                                           ▼
                      ┌─────────────────┐                          ┌──────────────┐
                      │   S3 Reports    │◀─────────────────────────│    Email/    │
                      │     Bucket      │                          │    Slack     │
                      └─────────────────┘                          └──────────────┘
```

## Azure Support

The collector can now run against Azure subscriptions. Set the environment variable
`CLOUD_PROVIDER=azure` and provide `AZURE_SUBSCRIPTION_ID` along with table configuration.
Resources will be gathered using Azure Functions, Cosmos DB, and Monitor equivalents.

## Features

### Core Features
- **Multi-Account Support**: Collect inventory from unlimited AWS accounts with retry logic
- **Automated Collection**: Multiple scheduled jobs for different purposes:
  - Inventory Collection (every 12 hours)
  - Cost Analysis (daily at 8 AM UTC)
  - Security Checks (weekly on Mondays)
  - Stale Resource Cleanup (monthly)
- **Resource Types Supported**:
  - EC2 Instances (state, type, utilization, cost tracking)
  - RDS Databases and Clusters (encryption, backup status)
  - S3 Buckets (size, encryption, public access, lifecycle)
  - Lambda Functions (invocations, errors, duration metrics)
- **Secure Cross-Account Access**: IAM role assumption with external ID
- **Serverless Architecture**: No infrastructure to manage
- **Cost Effective**: Typically < $20/month for most organizations

### Enhanced Features
- **Advanced Cost Analysis**:
  - Real-time cost estimation using AWS pricing
  - Identification of top expensive resources
  - Monthly/yearly cost projections
  - Department/tag-based cost allocation
  - Idle resource detection with savings estimates
  - Right-sizing recommendations
  
- **Security & Compliance**:
  - Automated weekly security scans
  - Unencrypted resource detection
  - Public access monitoring
  - Compliance violation alerts via SNS
  - Security dashboard metrics
  
- **Intelligent Querying**:
  - Global Secondary Indexes for fast queries
  - Query by resource type, department, or account
  - Advanced filtering (region, date range, tags)
  - Export to CSV with pandas integration
  - Cost analysis reports with visualizations
  
- **Monitoring & Observability**:
  - CloudWatch dashboard with 15+ metrics
  - Cost threshold alarms (configurable)
  - Collection failure detection
  - Performance tracking (duration, resource count)
  - Error rate monitoring
  
- **Automated Actions**:
  - Multiple Lambda actions (collect, analyze, check, cleanup)
  - Failed collection tracking and retry
  - Automated report generation to S3
  - Email and Slack notifications
  - Stale resource identification

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.9+ with pip
- Central AWS account for deployment
- AWS Organizations (optional but recommended)
- Email address for notifications

### 1. Clone and Setup

```bash
git clone <repository-url>
cd aws-multi-account-inventory
```

### 2. Configure Accounts

Copy and update the configuration file:

```bash
cp config/accounts.json.example config/accounts.json
```

Edit `config/accounts.json` with enhanced configuration:
```json
{
  "accounts": {
    "engineering": {
      "account_id": "123456789012",
      "role_name": "AWSInventoryRole",
      "enabled": true
    },
    "marketing": {
      "account_id": "234567890123",
      "role_name": "AWSInventoryRole",
      "enabled": true
    }
  },
  "resource_types": ["ec2", "rds", "s3", "lambda"],
  "excluded_regions": ["ap-south-2", "ap-southeast-4"],
  "collection_settings": {
    "parallel_regions": 10,
    "timeout_seconds": 300,
    "retry_attempts": 3
  },
  "cost_thresholds": {
    "expensive_resource_monthly": 100,
    "idle_resource_days": 30,
    "stale_resource_days": 90
  },
  "notifications": {
    "sns_topic_arn": "",
    "email_on_failure": true,
    "slack_webhook_url": ""
  }
}
```

### 3. Automated Deployment

Use the provided deployment script for a complete setup:

```bash
# Make script executable
chmod +x deploy.sh

# Run full deployment
./deploy.sh

# For Azure deployments
chmod +x scripts/deploy-azure.sh
./scripts/deploy-azure.sh

# The script will:
# - Check prerequisites
# - Create S3 artifacts bucket
# - Install dependencies
# - Run tests
# - Package Lambda function and layer
# - Deploy CloudFormation stack
# - Configure monitoring and alerts
```

### 4. Deploy Member Account Roles

For each member account, deploy the cross-account role:

```bash
# Using CloudFormation (in each member account)
aws cloudformation deploy \
  --template-file infrastructure/member-account-role.yaml \
  --stack-name aws-inventory-role \
  --parameter-overrides \
    MasterAccountId=YOUR_CENTRAL_ACCOUNT_ID \
    ExternalId=inventory-collector \
    OrganizationId=YOUR_ORG_ID \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile MEMBER_ACCOUNT_PROFILE
```

### 5. Verify Deployment

```bash
# Test inventory collection
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload '{"action": "collect"}' \
  output.json

# Check results
cat output.json | python -m json.tool

# View metrics dashboard
aws cloudwatch get-dashboard \
  --dashboard-name AWS-Inventory-Dashboard

# Check latest collection status
python -m src.query.inventory_query --action summary
```

## Usage

### Command Line Interface

Run inventory collection and queries locally:

```bash
# Run collection manually
python -m src.collector.enhanced_main --config config/accounts.json

# Show comprehensive summary
python -m src.query.inventory_query --action summary

# Detailed cost analysis
python -m src.query.inventory_query --action cost

# Security compliance report
python -m src.query.inventory_query --action security

# Find stale resources
python -m src.query.inventory_query --action stale --days 30

# Export filtered data
python -m src.query.inventory_query --action export \
  --resource-type ec2_instance \
  --department engineering \
  --output ec2-engineering.csv

# Query by various filters
python -m src.query.inventory_query --action query \
  --resource-type rds_instance \
  --region us-east-1 \
  --format json
```

### Lambda Function Actions

The Lambda function supports multiple actions via event payload:

```bash
# Inventory collection
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload '{"action": "collect"}' \
  response.json

# Cost analysis
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload '{"action": "cost_analysis"}' \
  response.json

# Security compliance check
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload '{"action": "security_check"}' \
  response.json

# Stale resource cleanup check
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload '{"action": "cleanup", "days": 90}' \
  response.json
```

### Advanced Queries

```bash
# Get top 10 most expensive resources
python -m src.query.inventory_query --action cost --format table | head -20

# Find all unencrypted resources
python -m src.query.inventory_query --action security | grep -i "unencrypted"

# Export cost report for finance
python -m src.query.inventory_query --action cost-report \
  --output monthly-costs-$(date +%Y%m).csv

# Department-specific analysis
python -m src.query.inventory_query --action query \
  --department marketing \
  --format json | jq '.[] | select(.estimated_monthly_cost > 50)'
```

## Configuration

### Environment Variables

Set these for Lambda function:

```bash
DYNAMODB_TABLE_NAME=aws-inventory
SNS_TOPIC_ARN=arn:aws:sns:region:account:topic
REPORT_BUCKET=aws-inventory-reports-account
MONTHLY_COST_THRESHOLD=10000
EXTERNAL_ID=inventory-collector
CONFIG_PATH=/opt/config/accounts.json  # Optional override for collector config
```

`CONFIG_PATH` allows you to point the Lambda function to a custom
`accounts.json` file. If omitted, `/opt/config/accounts.json` is used.

### Configuration File Structure

The `accounts.json` file supports these settings:

```json
{
  "accounts": {
    "account_name": {
      "account_id": "123456789012",
      "role_name": "AWSInventoryRole",
      "enabled": true,
      "tags": {
        "Department": "Engineering",
        "CostCenter": "1001"
      }
    }
  },
  "resource_types": ["ec2", "rds", "s3", "lambda"],
  "excluded_regions": ["ap-south-2"],
  "collection_settings": {
    "parallel_regions": 10,
    "timeout_seconds": 300,
    "retry_attempts": 3,
    "batch_size": 25
  },
  "cost_thresholds": {
    "expensive_resource_monthly": 100,
    "total_monthly_alert": 10000
  }
}
```

### Schedule Configuration

Configure different schedules in CloudFormation:

```yaml
Parameters:
  CollectionSchedule:
    Default: 'rate(12 hours)'
  CostAnalysisSchedule:
    Default: 'cron(0 8 * * ? *)'     # Daily at 8 AM
  SecurityCheckSchedule:
    Default: 'cron(0 10 * * MON *)'   # Weekly on Monday
  CleanupSchedule:
    Default: 'cron(0 6 1 * ? *)'      # Monthly on the 1st
```

## Extending the Collector

### Adding New Resource Types

1. **Add collection method** to `src/collector/enhanced_main.py`:
```python
def _collect_new_resource(self, session, account_id, account_name, region):
    """Collect new resource type with retry logic"""
    resources = []
    try:
        client = session.client('service-name', region_name=region)
        
        # Use pagination
        paginator = client.get_paginator('describe_resources')
        for page in paginator.paginate():
            for resource in page['Resources']:
                resources.append({
                    'resource_type': 'new_resource',
                    'resource_id': resource['ResourceId'],
                    'account_id': account_id,
                    'account_name': account_name,
                    'department': account_name,  # For GSI
                    'region': region,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'attributes': {
                        'name': resource.get('Name'),
                        'state': resource.get('State'),
                        'tags': self._process_tags(resource.get('Tags', []))
                    },
                    'estimated_monthly_cost': self._estimate_cost(
                        'new_resource', 
                        resource
                    )
                })
    except Exception as e:
        logger.error(f"Error collecting new resources in {region}: {str(e)}")
    return resources
```

2. **Add cost estimation** in `_estimate_cost()`:
```python
elif resource_type == 'new_resource':
    # Add resource-specific pricing logic
    base_rate = 0.10  # per hour
    if attributes.get('type') == 'large':
        base_rate = 0.20
    return base_rate * 730  # monthly
```

3. **Update collection orchestration**:
```python
# In collect_inventory() method
if 'new_resource' in self.resource_types:
    for region in regions:
        futures.append(
            executor.submit(
                self._collect_new_resource, 
                session, account_id, account_name, region
            )
        )
```

4. **Update IAM policies** in `infrastructure/member-account-role.yaml`:
```yaml
- Effect: Allow
  Action:
    - service:DescribeResources
    - service:ListResources
    - service:GetResourceTags
  Resource: '*'
```

5. **Add unit tests**:
```python
@mock_service
def test_collect_new_resource(self, collector):
    """Test new resource collection"""
    # Mock service responses
    # Assert collection results
    # Verify cost calculation
```

6. **Deploy changes**:
```bash
# Run tests first
pytest tests/unit/test_enhanced_collector.py::test_collect_new_resource

# Deploy
./deploy.sh
```

### Adding New Query Capabilities

1. **Add to query tool** in `src/query/inventory_query.py`:
```python
def get_resources_by_custom_filter(self, filter_key, filter_value):
    """Query by custom attribute"""
    response = self.table.scan(
        FilterExpression=Attr(f'attributes.{filter_key}').eq(filter_value)
    )
    return self._process_items(response['Items'])
```

2. **Add CLI option**:
```python
@click.option('--custom-filter', nargs=2, help='Custom attribute filter')
def main(..., custom_filter):
    if custom_filter:
        resources = query.get_resources_by_custom_filter(*custom_filter)
```

## Cost Analysis & Optimization

### System Operating Costs

Monthly cost breakdown for the inventory system itself:

| Component | Estimated Cost | Notes |
|-----------|---------------|-------|
| Lambda Execution | $2-5 | All scheduled functions, ~20K invocations |
| DynamoDB | $5-15 | On-demand pricing, includes GSIs |
| CloudWatch Logs | $2-3 | 30-day retention |
| CloudWatch Metrics | $3-5 | Custom metrics and dashboards |
| S3 Reports | $1-2 | Compressed reports with lifecycle |
| SNS Notifications | <$1 | Email and API calls |
| **Total** | **$15-30/month** | For organizations with <1000 resources |

### Built-in Optimization Features

#### 1. Automated Cost Analysis
```bash
# Daily cost analysis with trends
aws lambda invoke \
  --function-name aws-inventory-collector \
  --payload '{"action": "cost_analysis"}' \
  response.json

# Results include:
# - Total monthly spend by service
# - Top 20 most expensive resources
# - Cost trends and projections
# - Savings opportunities
```

#### 2. Resource Optimization

**Idle Resource Detection**:
- EC2 instances stopped >30 days
- RDS instances with no connections
- Empty S3 buckets >90 days old
- Lambda functions with <10 invocations/month

**Right-sizing Recommendations**:
- Oversized EC2 instances (t3.2xlarge with <10% CPU)
- Over-provisioned RDS instances
- Lambda functions with excessive memory

**Example Query**:
```bash
# Find all optimization opportunities
python -m src.query.inventory_query --action cost

# Sample output:
# Idle Resources (15 found):
# - EC2: i-abc123 (stopped 45 days) - Save $50/month
# - RDS: db-prod (0 connections) - Save $200/month
# 
# Total Potential Savings: $1,250/month
```

#### 3. Department Cost Allocation

Track costs by department or cost center:
```bash
# Department breakdown
python -m src.query.inventory_query --action summary --format json | \
  jq '.cost_by_department'

# Generate department report
python -m src.query.inventory_query --action export \
  --department engineering \
  --output engineering-costs.csv
```

#### 4. Automated Actions

Configure automated responses to cost events:
```yaml
# In CloudFormation parameters:
CostThresholds:
  MonthlyLimit: 10000
  ResourceLimit: 500
  IdleResourceAction: "notify"  # or "stop"
```

### Cost Optimization Workflow

1. **Weekly Review**:
   ```bash
   # Run comprehensive cost analysis
   ./scripts/weekly-cost-review.sh
   ```

2. **Monthly Optimization**:
   ```bash
   # Identify and act on savings
   python -m src.tools.optimize_resources \
     --dry-run \
     --min-savings 50
   ```

3. **Quarterly Planning**:
   - Review Reserved Instance coverage
   - Analyze usage patterns
   - Plan capacity changes

## Troubleshooting

### Common Issues and Solutions

#### Lambda Timeout
```bash
# Check current timeout
aws lambda get-function-configuration \
  --function-name aws-inventory-collector \
  --query Timeout

# Increase timeout (max 900 seconds)
aws lambda update-function-configuration \
  --function-name aws-inventory-collector \
  --timeout 900
```

**Root Causes**:
- Too many accounts/regions
- Large number of resources
- Network latency

**Solutions**:
- Enable parallel region collection
- Reduce regions in config
- Increase Lambda memory (improves CPU)

#### Permission Errors

**Test Role Assumption**:
```bash
# Test from Lambda execution role
aws sts assume-role \
  --role-arn arn:aws:iam::123456789012:role/AWSInventoryRole \
  --role-session-name test \
  --external-id inventory-collector

# If fails, check trust policy
aws iam get-role \
  --role-name AWSInventoryRole \
  --query 'Role.AssumeRolePolicyDocument'
```

**Common Fixes**:
- Verify external ID matches
- Check organization ID in trust policy
- Ensure Lambda execution role has AssumeRole permission

#### Missing Resources

**Debug Collection**:
```bash
# Check CloudWatch logs
aws logs tail /aws/lambda/aws-inventory-collector \
  --filter-pattern "ERROR" \
  --since 1h

# Run targeted collection
python -m src.collector.enhanced_main \
  --account-id 123456789012 \
  --resource-type ec2 \
  --region us-east-1 \
  --debug
```

#### DynamoDB Throttling

**Check metrics**:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name UserErrors \
  --dimensions Name=TableName,Value=aws-inventory \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

**Solutions**:
- Switch to on-demand billing
- Implement exponential backoff
- Batch writes more efficiently

#### High Costs

**Analyze spending**:
```bash
# Check Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=aws-inventory-collector \
  --period 86400 \
  --statistics Sum \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-31T23:59:59Z
```

**Cost reduction**:
- Reduce collection frequency
- Limit resource types
- Enable S3 lifecycle policies

## Security

### Security Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│   KMS Key   │────▶│  DynamoDB    │◀────│   Lambda      │
│ (Encryption)│     │  Encrypted   │     │  (No Internet)│
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                    ┌──────────────┐              │ STS AssumeRole
                    │     S3       │              │ + External ID
                    │  Encrypted   │              ▼
                    │  Versioned   │     ┌────────────────┐
                    └──────────────┘     │ Target Account │
                                        │  Read-Only Role │
                                        └────────────────┘
```

### Security Controls

#### 1. Access Control
- **Principle of Least Privilege**: Lambda has only required permissions
- **Cross-Account Access**: External ID prevents confused deputy
- **No Persistent Credentials**: Uses temporary STS credentials
- **CloudTrail Logging**: All API calls are audited

#### 2. Data Protection
- **Encryption at Rest**:
  - DynamoDB: AWS managed encryption
  - S3: AES-256 server-side encryption
  - Lambda environment variables: KMS encrypted
- **Encryption in Transit**: All API calls use TLS 1.2+
- **No Sensitive Data**: No passwords, keys, or PII collected

#### 3. Compliance Monitoring

**Automated Security Checks**:
```bash
# Weekly security scan results
{
  "unencrypted_resources": [
    {"type": "rds", "id": "db-prod-1", "risk": "high"},
    {"type": "s3", "id": "logs-bucket", "risk": "medium"}
  ],
  "public_resources": [
    {"type": "s3", "id": "static-assets", "risk": "low"}
  ],
  "compliance_score": 85
}
```

**Security Metrics Dashboard**:
- Unencrypted resource count
- Public access violations
- Failed authentication attempts
- Unusual API activity

#### 4. Network Security
- **No Internet Access**: Lambda runs in AWS managed VPC
- **VPC Endpoints** (optional): Private connectivity to AWS services
- **No Inbound Connections**: Event-driven architecture
- **API Gateway** (optional): Rate limiting and authentication

### Security Best Practices

#### Regular Audits
```bash
# Monthly security audit script
./scripts/security-audit.sh

# Checks:
# - IAM role permissions
# - Resource encryption status
# - Public access settings
# - Unused roles/policies
# - CloudTrail compliance
```

#### Incident Response
1. **Detection**: CloudWatch alarms for anomalies
2. **Containment**: Automated Lambda function disable
3. **Investigation**: CloudTrail and VPC Flow Logs
4. **Recovery**: Restore from DynamoDB point-in-time
5. **Lessons Learned**: Update security controls

#### Compliance Frameworks
- **AWS Well-Architected**: Security pillar alignment
- **CIS AWS Foundations**: Benchmark compliance
- **SOC 2**: Audit trail and access controls
- **GDPR**: No personal data collection

## Performance & Scalability

### Performance Metrics

| Metric | Typical Value | Notes |
|--------|--------------|-------|
| Collection Time | 2-5 min | For 5 accounts, 10 regions |
| Resources/Second | 50-100 | With parallel collection |
| DynamoDB Write | 1000/sec | Batch write capacity |
| Query Response | <100ms | Using GSI indexes |
| Memory Usage | 256-512MB | Lambda function |

### Scaling Considerations

**For Large Organizations (>50 accounts)**:
1. **Parallel Execution**: 
   - Use Step Functions for orchestration
   - Split accounts into batches
   - Multiple Lambda concurrent executions

2. **Data Partitioning**:
   - Partition DynamoDB by date
   - Archive old data to S3
   - Use DynamoDB streams for real-time processing

3. **Performance Tuning**:
   ```python
   # config/accounts.json
   {
     "collection_settings": {
       "parallel_regions": 20,      # Increase parallelism
       "batch_size": 50,           # Larger DynamoDB batches
       "timeout_seconds": 600,     # Longer timeout
       "memory_mb": 1024          # More Lambda memory
     }
   }
   ```

## Monitoring & Alerting

### CloudWatch Dashboard

The system includes a comprehensive dashboard with:
- Collection success rate
- Resource count trends
- Cost analysis graphs
- Security compliance score
- Performance metrics

### Key Metrics to Monitor

```bash
# Collection health
aws cloudwatch get-metric-statistics \
  --namespace AWSInventory \
  --metric-name CollectionSuccess \
  --statistics Average \
  --period 3600

# Cost trends
aws cloudwatch get-metric-statistics \
  --namespace AWSInventory \
  --metric-name TotalMonthlyCost \
  --statistics Maximum \
  --period 86400
```

### Alert Configuration

| Alert | Threshold | Action |
|-------|-----------|--------|
| Collection Failure | 2 consecutive | Email + Slack |
| High Cost | >$10,000/month | Email + Report |
| Security Issues | >10 resources | Email + Ticket |
| Performance | >5 min duration | Investigation |

## Roadmap

### Planned Features

- [ ] Support for 20+ additional AWS services
- [ ] Real-time streaming with Kinesis
- [ ] Machine learning cost predictions
- [ ] Automated remediation actions
- [ ] Multi-cloud support (Azure, GCP)
- [ ] GraphQL API interface
- [ ] Advanced visualization dashboard
- [ ] Kubernetes resource tracking
- [ ] Container image scanning
- [ ] Compliance reporting (SOC2, ISO)

### Version History

- **v2.0** (Current): Enhanced features, cost analysis, security checks
- **v1.0**: Basic inventory collection
- **v0.9**: Initial beta release

## Support

### Getting Help

- **Documentation**: This README and code comments
- **Issues**: GitHub Issues for bug reports
- **Discussion**: GitHub Discussions for questions
- **Email**: support@example.com (update with your email)

### Common Questions

**Q: Can this work with AWS Control Tower?**
A: Yes, deploy the member role as a Control Tower customization.

**Q: How do I add custom tags to all resources?**
A: Modify the collector to merge account-level tags from config.

**Q: Can I use this with AWS SSO?**
A: Yes, configure your AWS CLI with SSO and run locally.

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone and setup
git clone <repo>
cd aws-multi-account-inventory

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linting
flake8 src/
black src/ --check
```

### Running Tests

Install the development dependencies first so coverage plugins are available:

```bash
pip install -r requirements-dev.txt
make test
```

`make test` runs the entire unit test suite with coverage enabled.

### Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS SDK for Python (Boto3) team
- Open source community contributors
- AWS Well-Architected Framework authors

---

**Note**: This is an enhanced version of the AWS Multi-Account Inventory System with advanced features for cost optimization, security compliance, and intelligent querying. For questions or support, please open an issue on GitHub.