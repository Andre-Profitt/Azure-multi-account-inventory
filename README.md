# AWS Multi-Account Inventory System

A serverless solution for collecting and analyzing cloud resources across multiple AWS or Azure accounts. The project stores inventory data in DynamoDB/Cosmos DB and provides cost and security insights.

## Overview

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│   EventBridge   │────▶│    Lambda    │────▶│   DynamoDB    │────▶│ CloudWatch    │
│  (Scheduled)    │     │   Function   │     │  Table + GSI  │     │   Metrics     │
└─────────────────┘     └──────┬───────┘     └───────────────┘     └──────────────┘
                              │                                          │
                              │ Assumes Role                              ▼
                              ▼                                   ┌──────────────┐
                     ┌─────────────────┐                         │     SNS      │
                     │  Target Account │                         │   Topics     │
                     │  InventoryRole  │                         └──────────────┘
                     └─────────────────┘                                   │
                                                                          ▼
                     ┌─────────────────┐                         ┌──────────────┐
                     │   S3 Reports    │◀────────────────────────│    Email/    │
                     │     Bucket      │                         │    Slack     │
                     └─────────────────┘                         └──────────────┘
```

Azure deployments use Cosmos DB and Lighthouse delegation:

```
┌────────────┐     ┌────────────────┐     ┌──────────────┐
│ Timer Job  │───▶│ Azure Function  │───▶│   Cosmos DB   │
└────────────┘     └──────┬─────────┘     └──────┬───────┘
                          │                     │
                          │ Uses Lighthouse     │
                          ▼                     ▼
                   ┌─────────────┐     ┌───────────────┐
                   │ ARG / Cost  │     │  Log Analytics │
                   └─────────────┘     └───────────────┘
```

See [FEATURES](docs/FEATURES.md) for full capabilities and [COST_ANALYSIS](docs/COST_ANALYSIS.md) for optimization details. Usage examples are available in [USAGE_EXAMPLES](docs/USAGE_EXAMPLES.md).

## Quick Start

### Prerequisites
- AWS CLI configured
- Python 3.9+
- Terraform or CloudFormation
- An AWS account (and optional Azure subscription)

### Clone and Install
```bash
git clone https://github.com/andre-profitt/aws-multi-account-inventory.git
cd aws-multi-account-inventory
pip install -r requirements.txt
```

### Configure Accounts
```bash
cp config/accounts.json.example config/accounts.json
# edit accounts.json with your account IDs and role names
```

### Deploy Infrastructure
```bash
chmod +x deploy.sh
./deploy.sh
```
Deploy cross-account roles in each member account using the template in `infrastructure/member-account-role.yaml`.

### Verify
```bash
aws lambda invoke --function-name aws-inventory-collector --payload '{"action": "collect"}' response.json
cat response.json
```

### Local Usage
```bash
make collect   # run collection locally
make query     # show inventory summary
```

For advanced configuration and Azure setup, consult the [deployment checklist](docs/DEPLOYMENT_CHECKLIST.md).

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Pull requests are welcome!

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Optional Azure Deployment
To inventory Azure resources, set `CLOUD_PROVIDER=azure` and provide the Azure subscription variables. A helper script is included:
```bash
./scripts/deploy-azure.sh
```
This script creates the Function App, Cosmos DB, and Event Grid trigger. Refer to the [deployment checklist](docs/DEPLOYMENT_CHECKLIST.md) for the full list of required roles and variables.

### Azure Quick Start
```bash
cp config/azure_subscriptions.json config/azure_subscriptions.json
export COSMOS_URL="https://your-account.documents.azure.com:443/"
POETRY run python -m src.azure_collect --config config/azure_subscriptions.json
```
The collector supports filters defined in `azure_subscriptions.json` and produces
the same JSON schema as the AWS collector.

Example Resource Graph query to list unattached disks:
`Resources | where type =~ 'Microsoft.Compute/disks' | where properties.diskState == 'Unattached' | where properties.timeCreated < ago(30d)`

Sample payload for Cost Management queries:
```json
{"type": "Usage", "dataSet": {"granularity": "Daily"}, "timeframe": "MonthToDate"}
```

## Running Tests
Install development requirements and run:
```bash
pip install -r requirements-dev.txt
make test
```


## Environment Variables
Common variables for the Lambda function:
```bash
DYNAMODB_TABLE_NAME=aws-inventory
SNS_TOPIC_ARN=arn:aws:sns:region:account:topic
REPORT_BUCKET=aws-inventory-reports
EXTERNAL_ID=inventory-collector
```

## Configuration File Example
`config/accounts.json` defines the accounts and settings:
```json
{
  "accounts": {
    "production": {"account_id": "111111111111", "role_name": "InventoryRole"}
  },
  "resource_types": ["ec2", "rds", "s3", "lambda"],
  "excluded_regions": ["ap-south-2"],
  "collection_settings": {"parallel_regions": 5, "timeout_seconds": 300}
}
```

For Azure deployments, create `config/azure_subscriptions.json`:
```json
{
  "subscriptions": {
    "production": {
      "subscription_id": "11111111-2222-3333-4444-555555555555",
      "enabled": true
    },
    "development": {
      "subscription_id": "66666666-7777-8888-9999-000000000000",
      "enabled": true
    }
  },
  "resource_types": [
    "Microsoft.Compute/virtualMachines",
    "Microsoft.Storage/storageAccounts",
    "Microsoft.Web/sites"
  ],
  "tag_filters": {
    "Environment": ["Prod", "Dev"],
    "Owner": ["TeamA"]
  },
  "excluded_regions": [
    "southindia",
    "germanynorth"
  ]
}
```
