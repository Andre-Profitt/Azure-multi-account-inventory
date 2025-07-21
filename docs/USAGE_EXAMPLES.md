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

