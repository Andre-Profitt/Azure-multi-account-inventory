import json
import os
import traceback
from datetime import UTC, datetime
from typing import Any

import boto3
import structlog

from collector.enhanced_main import AWSInventoryCollector, AzureInventoryCollector
from common.logger import configure_logging
from query.enhanced_inventory_query import AzureInventoryQuery, InventoryQuery

configure_logging()
logger = structlog.get_logger(__name__)

# AWS clients will be initialized when needed
sns = None
cloudwatch = None
s3 = None

def get_clients() -> tuple[Any, Any, Any]:
    """Initialize AWS clients if not already done"""
    global sns, cloudwatch, s3
    if sns is None:
        sns = boto3.client('sns')
    if cloudwatch is None:
        cloudwatch = boto3.client('cloudwatch')
    if s3 is None:
        s3 = boto3.client('s3')
    return sns, cloudwatch, s3

def send_metric(metric_name: str, value: float, unit: str = 'Count') -> None:
    """Send custom metric to CloudWatch"""
    try:
        _, cloudwatch, _ = get_clients()
        cloudwatch.put_metric_data(
            Namespace='AWSInventory',
            MetricData=[
                {
                    'MetricName': metric_name,
                    'Value': value,
                    'Unit': unit,
                    'Timestamp': datetime.now(UTC)
                }
            ]
        )
    except Exception as e:
        logger.warning("Failed to send metric", metric=metric_name, error=str(e))

def send_notification(subject: str, message: str) -> None:
    """Send SNS notification"""
    topic_arn = os.environ.get('SNS_TOPIC_ARN')
    if topic_arn:
        try:
            sns, _, _ = get_clients()
            sns.publish(
                TopicArn=topic_arn,
                Subject=subject,
                Message=message
            )
        except Exception as e:
            logger.warning("Failed to send notification", error=str(e))

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Enhanced Lambda handler for scheduled collection"""
    start_time = datetime.now(UTC)
    action = event.get('action', 'collect')

    # Log invocation
    logger.info("Starting inventory", action=action, start=str(start_time))
    logger.debug("Event", event=event)

    try:
        if action == 'collect':
            return handle_collection(event, context, start_time)
        if action == 'cost_analysis':
            return handle_cost_analysis(event, context)
        if action == 'security_check':
            return handle_security_check(event, context)
        if action == 'cleanup':
            return handle_cleanup(event, context)
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Unknown action: {action}'})
        }
    except Exception as e:
        handle_error(e, action, context)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'request_id': context.aws_request_id
            })
        }

def handle_collection(event: dict[str, Any], _context: Any, start_time: datetime) -> dict[str, Any]:
    """Handle inventory collection"""
    # Initialize collector
    if os.environ.get('CLOUD_PROVIDER') == 'azure':
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        table_url = os.environ.get('AZURE_TABLE_URL')
        table_name = os.environ.get('AZURE_TABLE_NAME', 'inventory')
        collector = AzureInventoryCollector(subscription_id, table_url, table_name)
    else:
        collector = AWSInventoryCollector(
            table_name=os.environ.get('DYNAMODB_TABLE_NAME', 'aws-inventory')
        )

    # Load configuration
    config_path = os.environ.get('CONFIG_PATH', '/opt/config/accounts.json')
    if os.path.exists(config_path):
        collector.load_config(config_path)
    else:
        # Try loading from event
        if 'accounts' in event:
            collector.accounts = event['accounts']
            collector.resource_types = event.get('resource_types', ['ec2', 'rds', 's3', 'lambda'])
            collector.excluded_regions = event.get('excluded_regions', [])
        else:
            raise ValueError("No configuration found")

    # Run collection
    inventory = collector.collect_inventory()

    # Calculate metrics
    duration = (datetime.now(UTC) - start_time).total_seconds()
    resources_collected = len(inventory)
    failed_accounts = len(collector.failed_collections)

    # Send metrics to CloudWatch
    send_metric('CollectionDuration', duration, 'Seconds')
    send_metric('ResourcesCollected', resources_collected)
    send_metric('FailedAccounts', failed_accounts)
    send_metric('CollectionSuccess', 1 if failed_accounts == 0 else 0)

    # Group resources by type for metrics
    resources_by_type = {}
    total_cost = 0
    for item in inventory:
        resource_type = item.get('resource_type', 'unknown')
        resources_by_type[resource_type] = resources_by_type.get(resource_type, 0) + 1
        total_cost += item.get('estimated_monthly_cost', 0)

    # Send per-type metrics
    for resource_type, count in resources_by_type.items():
        send_metric(f'Resources_{resource_type}', count)

    # Send cost metric
    send_metric('TotalMonthlyCost', total_cost, 'None')

    # Log summary
    summary = {
        'duration_seconds': duration,
        'total_resources': resources_collected,
        'resources_by_type': resources_by_type,
        'failed_accounts': failed_accounts,
        'total_monthly_cost': total_cost,
    }
    logger.info("Collection completed", summary=summary)

    # Send notification if there were failures
    if failed_accounts > 0:
        failure_details = "\n".join([
            f"- {f['department']} ({f['account_id']}): {f['error']}"
            for f in collector.failed_collections
        ])

        send_notification(
            subject=f"AWS Inventory Collection - {failed_accounts} Account(s) Failed",
            message=f"""Inventory collection completed with failures.

Summary:
- Total resources collected: {resources_collected}
- Failed accounts: {failed_accounts}
- Duration: {duration:.2f} seconds
- Total monthly cost: ${total_cost:,.2f}

Failed Accounts:
{failure_details}

Please check CloudWatch logs for more details."""
        )

    # Return success response
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Collection completed successfully',
            'resources_collected': resources_collected,
            'duration_seconds': duration,
            'failed_accounts': failed_accounts,
            'total_monthly_cost': total_cost
        })
    }

def handle_cost_analysis(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Handle cost analysis and reporting"""
    logger.info("Starting cost analysis")

    if os.environ.get('CLOUD_PROVIDER') == 'azure':
        table_url = os.environ.get('AZURE_TABLE_URL')
        table_name = os.environ.get('AZURE_TABLE_NAME', 'inventory')
        query = AzureInventoryQuery(table_url, table_name)
    else:
        query = InventoryQuery(
            table_name=os.environ.get('DYNAMODB_TABLE_NAME', 'aws-inventory')
        )
    analysis = query.get_cost_analysis()

    # Calculate total monthly cost
    total_cost = analysis.get('total_monthly_cost', 0)

    # Send cost metrics
    send_metric('TotalMonthlyCost', total_cost, 'None')
    send_metric('ExpensiveResources', len(analysis.get('top_expensive_resources', [])))
    send_metric('IdleResources', len(analysis.get('idle_resources', [])))
    send_metric('UnencryptedResources', len(analysis.get('unencrypted_resources', [])))

    # Check if cost exceeds threshold
    cost_threshold = float(os.environ.get('MONTHLY_COST_THRESHOLD', '10000'))

    if total_cost > cost_threshold:
        # Build cost breakdown message
        cost_breakdown = "\n".join([
            f"- {rtype}: ${cost:.2f}"
            for rtype, cost in sorted(analysis['cost_by_type'].items(),
                                     key=lambda x: x[1], reverse=True)[:5]
        ])

        send_notification(
            subject=f"AWS Cost Alert - Monthly cost ${total_cost:.2f} exceeds threshold",
            message=f"""Monthly AWS costs have exceeded the threshold of ${cost_threshold:.2f}.

Current monthly cost: ${total_cost:.2f}
Projected annual cost: ${total_cost * 12:.2f}

Top 5 Resource Types by Cost:
{cost_breakdown}

Optimization Opportunities:
- Idle Resources: {len(analysis['idle_resources'])}
- Oversized Resources: {len(analysis['oversized_resources'])}
- Unencrypted Resources: {len(analysis['unencrypted_resources'])}

Please review the cost analysis dashboard for more details."""
        )

    # Generate and save cost report
    report_bucket = os.environ.get('REPORT_BUCKET')
    if report_bucket:
        report_key = f"cost-reports/{datetime.now(UTC).strftime('%Y/%m/%d')}/cost_analysis.json"

        _, _, s3 = get_clients()
        s3.put_object(
            Bucket=report_bucket,
            Key=report_key,
            Body=json.dumps(analysis, default=str),
            ContentType='application/json'
        )

        logger.info(
            "Cost analysis completed", report_location=f"s3://{report_bucket}/{report_key}"
        )

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Cost analysis completed',
            'total_monthly_cost': total_cost,
            'report_location': f"s3://{report_bucket}/{report_key}" if report_bucket else None
        })
    }

def handle_security_check(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Handle security compliance check"""
    logger.info("Starting security compliance check")

    if os.environ.get('CLOUD_PROVIDER') == 'azure':
        table_url = os.environ.get('AZURE_TABLE_URL')
        table_name = os.environ.get('AZURE_TABLE_NAME', 'inventory')
        query = AzureInventoryQuery(table_url, table_name)
    else:
        query = InventoryQuery(
            table_name=os.environ.get('DYNAMODB_TABLE_NAME', 'aws-inventory')
        )
    analysis = query.get_cost_analysis()

    # Count security issues
    unencrypted_count = len(analysis['unencrypted_resources'])
    public_count = len(analysis['public_resources'])
    total_issues = unencrypted_count + public_count

    # Send metrics
    send_metric('UnencryptedResources', unencrypted_count)
    send_metric('PublicResources', public_count)
    send_metric('SecurityIssues', total_issues)

    if total_issues > 0:
        # Build security issues message
        issues_message = []

        if unencrypted_count > 0:
            issues_message.append(f"\nUnencrypted Resources ({unencrypted_count}):")
            for r in analysis['unencrypted_resources'][:10]:
                issues_message.append(f"- {r['resource_id']} ({r['type']}) in {r['department']}")
            if unencrypted_count > 10:
                issues_message.append(f"... and {unencrypted_count - 10} more")

        if public_count > 0:
            issues_message.append(f"\nPublic Resources ({public_count}):")
            for r in analysis['public_resources'][:10]:
                issues_message.append(f"- {r['resource_id']} ({r['type']}) in {r['department']}")
            if public_count > 10:
                issues_message.append(f"... and {public_count - 10} more")

        send_notification(
            subject=f"AWS Security Alert - {total_issues} compliance issues found",
            message=f"""Security compliance check found {total_issues} issues requiring attention.

Summary:
- Unencrypted Resources: {unencrypted_count}
- Public Resources: {public_count}

Issues Found:
{chr(10).join(issues_message)}

Please review these resources and apply appropriate security measures."""
        )

    # Save security report
    report_bucket = os.environ.get('REPORT_BUCKET')
    if report_bucket:
        report_key = f"security-reports/{datetime.now(UTC).strftime('%Y/%m/%d')}/security_check.json"

        security_report = {
            'timestamp': datetime.now(UTC).isoformat(),
            'total_issues': total_issues,
            'unencrypted_resources': analysis['unencrypted_resources'],
            'public_resources': analysis['public_resources']
        }

        _, _, s3 = get_clients()
        s3.put_object(
            Bucket=report_bucket,
            Key=report_key,
            Body=json.dumps(security_report, default=str),
            ContentType='application/json'
        )

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Security check completed',
            'total_issues': total_issues,
            'unencrypted_count': unencrypted_count,
            'public_count': public_count
        })
    }

def handle_cleanup(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Handle stale resource cleanup"""
    logger.info("Starting stale resource check")

    if os.environ.get('CLOUD_PROVIDER') == 'azure':
        table_url = os.environ.get('AZURE_TABLE_URL')
        table_name = os.environ.get('AZURE_TABLE_NAME', 'inventory')
        query = AzureInventoryQuery(table_url, table_name)
    else:
        query = InventoryQuery(
            table_name=os.environ.get('DYNAMODB_TABLE_NAME', 'aws-inventory')
        )

    days = event.get('days', 90)
    stale_resources = query.get_stale_resources(days)

    # Send metrics
    send_metric('StaleResources', len(stale_resources))

    if stale_resources:
        # Group by type
        stale_by_type = {}
        for r in stale_resources:
            rtype = r['resource_type']
            stale_by_type[rtype] = stale_by_type.get(rtype, 0) + 1

        breakdown = "\n".join([
            f"- {rtype}: {count}"
            for rtype, count in sorted(stale_by_type.items(), key=lambda x: x[1], reverse=True)
        ])

        details = chr(10).join(
            [
                f"- {r['resource_id']} ({r['resource_type']}) - {r['age_days']} days old"
                for r in stale_resources[:10]
            ]
        )
        send_notification(
            subject=f"AWS Cleanup Alert - {len(stale_resources)} stale resources found",
            message=(
                f"Found {len(stale_resources)} resources that haven't been modified in over {days} days.\n\n"
                f"Breakdown by Type:\n{breakdown}\n\nTop Stale Resources:\n{details}\n\n"
                "Consider reviewing these resources for potential cleanup."
            ),
        )

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Cleanup check completed',
            'stale_resources': len(stale_resources),
            'threshold_days': days
        })
    }

def handle_error(error: Exception, action: str, context: Any) -> None:
    """Handle and report errors"""
    error_message = f"{action} failed: {str(error)}\n{traceback.format_exc()}"
    logger.error(error_message)

    # Send failure metric
    send_metric('CollectionSuccess', 0)
    send_metric('CollectionErrors', 1)

    # Send notification
    send_notification(
        subject=f"AWS Inventory {action.title()} Failed",
        message=f"""Inventory {action} failed with error.

Error: {str(error)}

Please check CloudWatch logs for full stack trace.

Function: {context.function_name}
Request ID: {context.aws_request_id}"""
    )


