#!/usr/bin/env python3
"""Enhanced AWS Inventory Query Tool with cost analysis and advanced filtering"""

import json
from collections import defaultdict
from datetime import timezone
from datetime import datetime
from datetime import timedelta

UTC = timezone.utc
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
import click
import pandas as pd
from tabulate import tabulate
from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential


class InventoryQuery:
    """Query tool for AWS inventory data with cost analysis capabilities"""

    def __init__(self, table_name: str = 'aws-inventory'):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)

    def _decimal_to_float(self, obj):
        """Convert DynamoDB Decimal types to float for JSON serialization"""
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: self._decimal_to_float(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._decimal_to_float(v) for v in obj]
        return obj

    def get_all_items(self, filter_expression=None) -> List[Dict]:
        """Get all items from DynamoDB with optional filter"""
        items = []

        scan_kwargs = {}
        if filter_expression:
            scan_kwargs['FilterExpression'] = filter_expression

        response = self.table.scan(**scan_kwargs)
        items.extend(response['Items'])

        while 'LastEvaluatedKey' in response:
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            response = self.table.scan(**scan_kwargs)
            items.extend(response['Items'])

        return [self._decimal_to_float(item) for item in items]

    def get_summary(self) -> Dict[str, Any]:
        """Get inventory summary with cost analysis"""
        items = self.get_all_items()

        summary = {
            'total_resources': len(items),
            'by_type': defaultdict(int),
            'by_account': defaultdict(int),
            'by_region': defaultdict(int),
            'total_monthly_cost': 0,
            'cost_by_type': defaultdict(float),
            'cost_by_account': defaultdict(float),
            'cost_by_region': defaultdict(float),
            'timestamp': datetime.now(UTC).isoformat()
        }

        for item in items:
            resource_type = item.get('resource_type', 'unknown')
            account_name = item.get('account_name', 'unknown')
            region = item.get('region', 'unknown')
            monthly_cost = item.get('estimated_monthly_cost', 0)

            summary['by_type'][resource_type] += 1
            summary['by_account'][account_name] += 1
            summary['by_region'][region] += 1

            summary['total_monthly_cost'] += monthly_cost
            summary['cost_by_type'][resource_type] += monthly_cost
            summary['cost_by_account'][account_name] += monthly_cost
            summary['cost_by_region'][region] += monthly_cost

        # Convert defaultdicts to regular dicts for JSON serialization
        summary['by_type'] = dict(summary['by_type'])
        summary['by_account'] = dict(summary['by_account'])
        summary['by_region'] = dict(summary['by_region'])
        summary['cost_by_type'] = dict(summary['cost_by_type'])
        summary['cost_by_account'] = dict(summary['cost_by_account'])
        summary['cost_by_region'] = dict(summary['cost_by_region'])

        return summary

    def get_cost_analysis(self) -> Dict[str, Any]:
        """Perform detailed cost analysis with optimization recommendations"""
        items = self.get_all_items()

        analysis = {
            'total_monthly_cost': 0,
            'yearly_projection': 0,
            'top_expensive_resources': [],
            'cost_optimization_opportunities': [],
            'idle_resources': [],
            'oversized_resources': [],
            'unencrypted_resources': [],
            'public_resources': []
        }

        # Calculate costs and identify issues
        resources_with_cost = []

        for item in items:
            monthly_cost = item.get('estimated_monthly_cost', 0)
            analysis['total_monthly_cost'] += monthly_cost

            if monthly_cost > 0:
                resources_with_cost.append({
                    'resource_id': item.get('resource_id'),
                    'resource_type': item.get('resource_type'),
                    'account_name': item.get('account_name'),
                    'region': item.get('region'),
                    'monthly_cost': monthly_cost,
                    'attributes': item.get('attributes', {})
                })

            # Check for optimization opportunities
            attrs = item.get('attributes', {})
            resource_type = item.get('resource_type', '')

            # Idle EC2 instances
            if resource_type == 'ec2_instance':
                state = attrs.get('state', '')
                if state == 'stopped':
                    launch_time = attrs.get('launch_time', '')
                    if launch_time:
                        launch_date = datetime.fromisoformat(launch_time.replace('Z', '+00:00'))
                        days_stopped = (datetime.now(UTC) - launch_date).days
                        if days_stopped > 30:
                            analysis['idle_resources'].append({
                                'resource_id': item.get('resource_id'),
                                'type': 'EC2 Instance',
                                'reason': f'Stopped for {days_stopped} days',
                                'recommendation': 'Consider terminating or creating an AMI',
                                'potential_savings': 0  # No cost for stopped instances
                            })

                # Oversized instances (simple heuristic)
                instance_type = attrs.get('instance_type', '')
                if instance_type.startswith(('m5.2xlarge', 'm5.4xlarge', 'm5.8xlarge')):
                    analysis['oversized_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'EC2 Instance',
                        'current_type': instance_type,
                        'recommendation': 'Review CPU/memory utilization, consider downsizing',
                        'potential_savings': monthly_cost * 0.3  # Assume 30% savings
                    })

            # Unencrypted RDS instances
            if resource_type == 'rds_instance':
                if not attrs.get('storage_encrypted', False):
                    analysis['unencrypted_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'RDS Instance',
                        'issue': 'Storage not encrypted',
                        'recommendation': 'Enable encryption for compliance'
                    })

            # Unencrypted S3 buckets
            if resource_type == 's3_bucket':
                if not attrs.get('encryption', False):
                    analysis['unencrypted_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'S3 Bucket',
                        'issue': 'Bucket not encrypted',
                        'recommendation': 'Enable default encryption'
                    })

                # Public S3 buckets
                if attrs.get('public_access', False):
                    analysis['public_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'S3 Bucket',
                        'issue': 'Public access enabled',
                        'recommendation': 'Review and restrict public access'
                    })

            # Low-utilization Lambda functions
            if resource_type == 'lambda_function':
                invocations = attrs.get('invocations_monthly', 0)
                if invocations < 10 and monthly_cost > 0:
                    analysis['idle_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'Lambda Function',
                        'reason': f'Only {invocations} invocations/month',
                        'recommendation': 'Consider removing unused function',
                        'potential_savings': monthly_cost
                    })

        # Sort and get top expensive resources
        resources_with_cost.sort(key=lambda x: x['monthly_cost'], reverse=True)
        analysis['top_expensive_resources'] = resources_with_cost[:20]

        # Calculate yearly projection
        analysis['yearly_projection'] = analysis['total_monthly_cost'] * 12

        # Calculate total potential savings
        total_savings = sum(r.get('potential_savings', 0) for r in analysis['idle_resources'])
        total_savings += sum(r.get('potential_savings', 0) for r in analysis['oversized_resources'])

        analysis['total_potential_savings'] = total_savings
        analysis['yearly_potential_savings'] = total_savings * 12

        return analysis

    def get_resources_by_filter(self, account_id: Optional[str] = None,
                               resource_type: Optional[str] = None,
                               region: Optional[str] = None,
                               days: Optional[int] = None) -> List[Dict]:
        """Get resources with multiple filter options"""
        filter_parts = []
        expression_values = {}

        if account_id:
            filter_parts.append('account_id = :account_id')
            expression_values[':account_id'] = account_id

        if resource_type:
            filter_parts.append('resource_type = :resource_type')
            expression_values[':resource_type'] = resource_type

        if region:
            filter_parts.append('region = :region')
            expression_values[':region'] = region

        if days:
            cutoff_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            filter_parts.append('timestamp > :cutoff')
            expression_values[':cutoff'] = cutoff_date

        if filter_parts:
            from boto3.dynamodb.conditions import Attr
            filter_expression = None

            # Build filter expression dynamically
            for part in filter_parts:
                if 'account_id' in part:
                    expr = Attr('account_id').eq(expression_values[':account_id'])
                elif 'resource_type' in part:
                    expr = Attr('resource_type').eq(expression_values[':resource_type'])
                elif 'region' in part:
                    expr = Attr('region').eq(expression_values[':region'])
                elif 'timestamp' in part:
                    expr = Attr('timestamp').gt(expression_values[':cutoff'])

                filter_expression = expr if filter_expression is None else filter_expression & expr

            return self.get_all_items(filter_expression)

        return self.get_all_items()


class AzureInventoryQuery:
    """Query tool for Azure inventory data stored in Table Storage"""

    def __init__(self, table_url: str, table_name: str):
        credential = DefaultAzureCredential()
        service = TableServiceClient(endpoint=table_url, credential=credential)
        self.table = service.get_table_client(table_name)

    def get_all_items(self) -> List[Dict]:
        entities = []
        for entity in self.table.list_entities():
            entities.append(dict(entity))
        return entities

    def export_to_csv(self, filename: str, resources: List[Dict]):
        """Export resources to CSV file"""
        if not resources:
            click.echo("No resources to export")
            return

        # Flatten the data for CSV export
        flattened_data = []

        for resource in resources:
            flat_resource = {
                'resource_type': resource.get('resource_type'),
                'resource_id': resource.get('resource_id'),
                'account_id': resource.get('account_id'),
                'account_name': resource.get('account_name'),
                'region': resource.get('region'),
                'timestamp': resource.get('timestamp'),
                'estimated_monthly_cost': resource.get('estimated_monthly_cost', 0)
            }

            # Add selected attributes
            attrs = resource.get('attributes', {})
            if resource.get('resource_type') == 'ec2_instance':
                flat_resource.update({
                    'instance_type': attrs.get('instance_type'),
                    'state': attrs.get('state'),
                    'platform': attrs.get('platform'),
                    'vpc_id': attrs.get('vpc_id')
                })
            elif resource.get('resource_type') == 'rds_instance':
                flat_resource.update({
                    'engine': attrs.get('engine'),
                    'instance_class': attrs.get('instance_class'),
                    'status': attrs.get('status'),
                    'storage_encrypted': attrs.get('storage_encrypted')
                })
            elif resource.get('resource_type') == 's3_bucket':
                flat_resource.update({
                    'size_gb': attrs.get('size_gb'),
                    'versioning': attrs.get('versioning'),
                    'encryption': attrs.get('encryption'),
                    'public_access': attrs.get('public_access')
                })
            elif resource.get('resource_type') == 'lambda_function':
                flat_resource.update({
                    'function_name': attrs.get('function_name'),
                    'runtime': attrs.get('runtime'),
                    'memory_size': attrs.get('memory_size'),
                    'invocations_monthly': attrs.get('invocations_monthly')
                })

            # Add tags
            tags = attrs.get('tags', {})
            flat_resource['department'] = tags.get('Department', '')
            flat_resource['environment'] = tags.get('Environment', '')
            flat_resource['owner'] = tags.get('Owner', '')

            flattened_data.append(flat_resource)

        # Create DataFrame and export to CSV
        df = pd.DataFrame(flattened_data)
        df.to_csv(filename, index=False)

        click.echo(f"Exported {len(resources)} resources to {filename}")

    def get_stale_resources(self, days: int = 90) -> List[Dict]:
        """Find resources that haven't been used in specified days"""
        items = self.get_all_items()
        stale_resources = []

        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        for item in items:
            attrs = item.get('attributes', {})
            resource_type = item.get('resource_type', '')

            is_stale = False
            stale_reason = ''

            if resource_type == 'ec2_instance':
                # Check if stopped for too long
                if attrs.get('state') == 'stopped':
                    launch_time = attrs.get('launch_time')
                    if launch_time:
                        launch_date = datetime.fromisoformat(launch_time.replace('Z', '+00:00'))
                        if launch_date < cutoff_date:
                            is_stale = True
                            stale_reason = f"Stopped since {launch_time}"

            elif resource_type == 'lambda_function':
                # Check invocation count
                invocations = attrs.get('invocations_monthly', 0)
                if invocations == 0:
                    is_stale = True
                    stale_reason = "No invocations in last month"

            elif resource_type == 's3_bucket':
                # Check if empty bucket
                size_bytes = attrs.get('size_bytes', 0)
                creation_date = attrs.get('creation_date')
                if size_bytes == 0 and creation_date:
                    create_date = datetime.fromisoformat(creation_date.replace('Z', '+00:00'))
                    if create_date < cutoff_date:
                        is_stale = True
                        stale_reason = f"Empty bucket created on {creation_date}"

            if is_stale:
                stale_resources.append({
                    'resource_type': resource_type,
                    'resource_id': item.get('resource_id'),
                    'account_name': item.get('account_name'),
                    'region': item.get('region'),
                    'reason': stale_reason,
                    'monthly_cost': item.get('estimated_monthly_cost', 0),
                    'attributes': attrs
                })

        return stale_resources


@click.command()
@click.option('--table', default='aws-inventory', help='DynamoDB table name')
@click.option('--action', type=click.Choice([
    'summary', 'by-account', 'by-type', 'by-region', 'recent',
    'export', 'details', 'cost', 'stale', 'security'
]), default='summary', help='Query action to perform')
@click.option('--account-id', help='Filter by account ID')
@click.option('--account-name', help='Filter by account name')
@click.option('--resource-type', help='Filter by resource type')
@click.option('--resource-id', help='Get details for specific resource')
@click.option('--region', help='Filter by region')
@click.option('--hours', type=int, help='Show resources from last N hours')
@click.option('--days', type=int, help='Show resources from last N days')
@click.option('--output', help='Output filename for export')
@click.option('--format', type=click.Choice(['json', 'csv', 'table']), default='table',
              help='Output format')
@click.option('--department', help='Filter by Department tag')
@click.option('--environment', help='Filter by Environment tag')
def main(table, action, account_id, account_name, resource_type, resource_id,
         region, hours, days, output, format, department, environment):
    """Enhanced AWS Inventory Query Tool"""

    query = InventoryQuery(table_name=table)

    if action == 'summary':
        summary = query.get_summary()

        if format == 'json':
            click.echo(json.dumps(summary, indent=2, default=str))
        else:
            click.echo("\n=== AWS Inventory Summary ===")
            click.echo(f"Total Resources: {summary['total_resources']}")
            click.echo(f"Total Monthly Cost: ${summary['total_monthly_cost']:,.2f}")
            click.echo(f"Yearly Projection: ${summary['total_monthly_cost'] * 12:,.2f}")

            click.echo("\n--- Resources by Type ---")
            for rtype, count in sorted(summary['by_type'].items()):
                cost = summary['cost_by_type'].get(rtype, 0)
                click.echo(f"{rtype}: {count} (${cost:,.2f}/month)")

            click.echo("\n--- Resources by Account ---")
            for account, count in sorted(summary['by_account'].items()):
                cost = summary['cost_by_account'].get(account, 0)
                click.echo(f"{account}: {count} (${cost:,.2f}/month)")

            click.echo("\n--- Top Regions by Cost ---")
            sorted_regions = sorted(summary['cost_by_region'].items(),
                                  key=lambda x: x[1], reverse=True)[:5]
            for region, cost in sorted_regions:
                click.echo(f"{region}: ${cost:,.2f}/month")

    elif action == 'cost':
        analysis = query.get_cost_analysis()

        if format == 'json':
            click.echo(json.dumps(analysis, indent=2, default=str))
        else:
            click.echo("\n=== Cost Analysis Report ===")
            click.echo(f"Total Monthly Cost: ${analysis['total_monthly_cost']:,.2f}")
            click.echo(f"Yearly Projection: ${analysis['yearly_projection']:,.2f}")
            click.echo(f"Potential Monthly Savings: ${analysis['total_potential_savings']:,.2f}")
            click.echo(f"Potential Yearly Savings: ${analysis['yearly_potential_savings']:,.2f}")

            click.echo("\n--- Top 10 Most Expensive Resources ---")
            for i, resource in enumerate(analysis['top_expensive_resources'][:10], 1):
                click.echo(f"{i}. {resource['resource_type']} - {resource['resource_id']}")
                click.echo(f"   Account: {resource['account_name']}, Region: {resource['region']}")
                click.echo(f"   Cost: ${resource['monthly_cost']:,.2f}/month")

            if analysis['idle_resources']:
                click.echo(f"\n--- Idle Resources ({len(analysis['idle_resources'])}) ---")
                for resource in analysis['idle_resources'][:5]:
                    click.echo(f"• {resource['type']} - {resource['resource_id']}")
                    click.echo(f"  Reason: {resource['reason']}")
                    click.echo(f"  Recommendation: {resource['recommendation']}")
                    if resource.get('potential_savings'):
                        click.echo(f"  Potential Savings: ${resource['potential_savings']:,.2f}/month")

            if analysis['oversized_resources']:
                click.echo(f"\n--- Potentially Oversized Resources ({len(analysis['oversized_resources'])}) ---")
                for resource in analysis['oversized_resources'][:5]:
                    click.echo(f"• {resource['type']} - {resource['resource_id']}")
                    click.echo(f"  Current: {resource['current_type']}")
                    click.echo(f"  Recommendation: {resource['recommendation']}")
                    click.echo(f"  Potential Savings: ${resource['potential_savings']:,.2f}/month")

    elif action == 'security':
        analysis = query.get_cost_analysis()

        click.echo("\n=== Security Analysis Report ===")

        if analysis['unencrypted_resources']:
            click.echo(f"\n--- Unencrypted Resources ({len(analysis['unencrypted_resources'])}) ---")
            for resource in analysis['unencrypted_resources']:
                click.echo(f"• {resource['type']} - {resource['resource_id']}")
                click.echo(f"  Issue: {resource['issue']}")
                click.echo(f"  Recommendation: {resource['recommendation']}")

        if analysis['public_resources']:
            click.echo(f"\n--- Public Resources ({len(analysis['public_resources'])}) ---")
            for resource in analysis['public_resources']:
                click.echo(f"• {resource['type']} - {resource['resource_id']}")
                click.echo(f"  Issue: {resource['issue']}")
                click.echo(f"  Recommendation: {resource['recommendation']}")

    elif action == 'stale':
        stale_days = days or 90
        stale_resources = query.get_stale_resources(stale_days)

        if format == 'json':
            click.echo(json.dumps(stale_resources, indent=2, default=str))
        else:
            click.echo(f"\n=== Stale Resources (>{stale_days} days) ===")
            click.echo(f"Found {len(stale_resources)} stale resources")

            total_cost = sum(r['monthly_cost'] for r in stale_resources)
            click.echo(f"Total monthly cost of stale resources: ${total_cost:,.2f}")

            for resource in stale_resources[:20]:
                click.echo(f"\n• {resource['resource_type']} - {resource['resource_id']}")
                click.echo(f"  Account: {resource['account_name']}, Region: {resource['region']}")
                click.echo(f"  Reason: {resource['reason']}")
                click.echo(f"  Monthly Cost: ${resource['monthly_cost']:,.2f}")

    elif action == 'export':
        # Build filters
        resources = query.get_resources_by_filter(
            account_id=account_id,
            resource_type=resource_type,
            region=region,
            days=days
        )

        # Apply tag filters if specified
        if department or environment:
            filtered_resources = []
            for resource in resources:
                tags = resource.get('attributes', {}).get('tags', {})
                if department and tags.get('Department') != department:
                    continue
                if environment and tags.get('Environment') != environment:
                    continue
                filtered_resources.append(resource)
            resources = filtered_resources

        if output:
            if output.endswith('.csv'):
                query.export_to_csv(output, resources)
            else:
                with open(output, 'w') as f:
                    json.dump(resources, f, indent=2, default=str)
                click.echo(f"Exported {len(resources)} resources to {output}")
        else:
            click.echo(json.dumps(resources, indent=2, default=str))

    elif action == 'details':
        if not resource_id:
            click.echo("Error: --resource-id required for details action")
            return

        # Find the resource
        items = query.get_all_items()
        resource = None

        for item in items:
            if item.get('resource_id') == resource_id:
                resource = item
                break

        if resource:
            if format == 'json':
                click.echo(json.dumps(resource, indent=2, default=str))
            else:
                click.echo("\n=== Resource Details ===")
                click.echo(f"Type: {resource.get('resource_type')}")
                click.echo(f"ID: {resource.get('resource_id')}")
                click.echo(f"Account: {resource.get('account_name')} ({resource.get('account_id')})")
                click.echo(f"Region: {resource.get('region')}")
                click.echo(f"Last Updated: {resource.get('timestamp')}")
                click.echo(f"Monthly Cost: ${resource.get('estimated_monthly_cost', 0):,.2f}")

                click.echo("\n--- Attributes ---")
                attrs = resource.get('attributes', {})
                for key, value in attrs.items():
                    if key != 'tags':
                        click.echo(f"{key}: {value}")

                tags = attrs.get('tags', {})
                if tags:
                    click.echo("\n--- Tags ---")
                    for key, value in tags.items():
                        click.echo(f"{key}: {value}")
        else:
            click.echo(f"Resource not found: {resource_id}")

    else:
        # Handle by-account, by-type, by-region, recent
        resources = query.get_resources_by_filter(
            account_id=account_id,
            resource_type=resource_type,
            region=region,
            days=days
        )

        if hours:
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            resources = [r for r in resources
                        if datetime.fromisoformat(r['timestamp'].replace('Z', '+00:00')) > cutoff]

        if action == 'by-account' and account_name:
            resources = [r for r in resources if r.get('account_name') == account_name]

        if format == 'json':
            click.echo(json.dumps(resources, indent=2, default=str))
        else:
            click.echo(f"\nFound {len(resources)} resources")

            if resources:
                # Create summary table
                table_data = []
                for r in resources[:50]:  # Limit table display
                    table_data.append([
                        r.get('resource_type'),
                        r.get('resource_id')[:40] + '...' if len(r.get('resource_id', '')) > 40 else r.get('resource_id'),
                        r.get('account_name'),
                        r.get('region'),
                        f"${r.get('estimated_monthly_cost', 0):,.2f}"
                    ])

                headers = ['Type', 'Resource ID', 'Account', 'Region', 'Monthly Cost']
                click.echo(tabulate(table_data, headers=headers, tablefmt='grid'))

                if len(resources) > 50:
                    click.echo(f"\n... and {len(resources) - 50} more resources")


if __name__ == '__main__':
    main()
