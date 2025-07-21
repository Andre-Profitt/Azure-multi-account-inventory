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

