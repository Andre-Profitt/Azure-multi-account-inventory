#!/usr/bin/env python3
"""Query AWS Inventory Data with Enhanced Features"""

import json
from collections import defaultdict
from datetime import timezone
from datetime import datetime
from datetime import timedelta

UTC = timezone.utc
from decimal import Decimal
from typing import Any

import boto3
import click
import pandas as pd
from boto3.dynamodb.conditions import Attr
from boto3.dynamodb.conditions import Key
from tabulate import tabulate


class InventoryQuery:
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

    def query_by_resource_type(self, resource_type: str) -> list[dict]:
        """Query resources by type using GSI"""
        items = []

        # Check if GSI exists, otherwise fall back to scan
        try:
            response = self.table.query(
                IndexName='resource-type-index',
                KeyConditionExpression=Key('resource_type').eq(resource_type)
            )
            items.extend(response.get('Items', []))

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.table.query(
                    IndexName='resource-type-index',
                    KeyConditionExpression=Key('resource_type').eq(resource_type),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))
        except:
            # Fallback to scan with filter
            response = self.table.scan(
                FilterExpression=Attr('resource_type').eq(resource_type)
            )
            items.extend(response.get('Items', []))

            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=Attr('resource_type').eq(resource_type),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))

        return [self._decimal_to_float(item) for item in items]

    def query_by_department(self, department: str) -> list[dict]:
        """Query resources by department using GSI"""
        items = []

        # Check if GSI exists, otherwise fall back to scan
        try:
            response = self.table.query(
                IndexName='department-index',
                KeyConditionExpression=Key('department').eq(department)
            )
            items.extend(response.get('Items', []))

            while 'LastEvaluatedKey' in response:
                response = self.table.query(
                    IndexName='department-index',
                    KeyConditionExpression=Key('department').eq(department),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))
        except:
            # Fallback to scan with filter
            response = self.table.scan(
                FilterExpression=Attr('department').eq(department) | Attr('account_name').eq(department)
            )
            items.extend(response.get('Items', []))

            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    FilterExpression=Attr('department').eq(department) | Attr('account_name').eq(department),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))

        return [self._decimal_to_float(item) for item in items]

    def get_all_resources(self) -> list[dict]:
        """Get all resources (use with caution on large datasets)"""
        items = []
        response = self.table.scan()
        items.extend(response.get('Items', []))

        while 'LastEvaluatedKey' in response:
            response = self.table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        return [self._decimal_to_float(item) for item in items]

    def get_summary(self) -> dict[str, Any]:
        """Get comprehensive inventory summary"""
        all_items = self.get_all_resources()

        summary = {
            'total_resources': len(all_items),
            'by_type': defaultdict(int),
            'by_department': defaultdict(int),
            'by_region': defaultdict(int),
            'by_account': defaultdict(int),
            'total_estimated_cost': {
                'hourly': 0,
                'monthly': 0
            }
        }

        for item in all_items:
            # Count by type
            resource_type = item.get('resource_type', 'unknown')
            summary['by_type'][resource_type] += 1

            # Count by department/account name
            department = item.get('department') or item.get('account_name', 'unknown')
            summary['by_department'][department] += 1

            # Count by region
            region = item.get('region', 'unknown')
            summary['by_region'][region] += 1

            # Count by account
            account = item.get('account_id', 'unknown')
            summary['by_account'][account] += 1

            # Sum costs
            if 'estimated_hourly_cost' in item:
                summary['total_estimated_cost']['hourly'] += float(item['estimated_hourly_cost'])
            if 'estimated_monthly_cost' in item:
                summary['total_estimated_cost']['monthly'] += float(item['estimated_monthly_cost'])

        # Calculate monthly from hourly if needed
        if summary['total_estimated_cost']['monthly'] == 0 and summary['total_estimated_cost']['hourly'] > 0:
            summary['total_estimated_cost']['monthly'] = summary['total_estimated_cost']['hourly'] * 730

        # Convert defaultdicts to regular dicts
        summary['by_type'] = dict(summary['by_type'])
        summary['by_department'] = dict(summary['by_department'])
        summary['by_region'] = dict(summary['by_region'])
        summary['by_account'] = dict(summary['by_account'])

        return summary

    def get_cost_analysis(self) -> dict[str, Any]:
        """Perform cost analysis and optimization recommendations"""
        all_items = self.get_all_resources()

        analysis = {
            'cost_by_type': defaultdict(float),
            'cost_by_department': defaultdict(float),
            'cost_by_region': defaultdict(float),
            'expensive_resources': [],
            'idle_resources': [],
            'oversized_resources': [],
            'unencrypted_resources': [],
            'public_resources': [],
            'optimization_opportunities': []
        }

        # Analyze each resource
        for item in all_items:
            resource_type = item.get('resource_type', 'unknown')
            department = item.get('department') or item.get('account_name', 'unknown')
            region = item.get('region', 'unknown')

            # Calculate monthly cost
            monthly_cost = 0
            if 'estimated_monthly_cost' in item:
                monthly_cost = float(item['estimated_monthly_cost'])
            elif 'estimated_hourly_cost' in item:
                monthly_cost = float(item['estimated_hourly_cost']) * 730

            # Track costs
            if monthly_cost > 0:
                analysis['cost_by_type'][resource_type] += monthly_cost
                analysis['cost_by_department'][department] += monthly_cost
                analysis['cost_by_region'][region] += monthly_cost

                # Flag expensive resources (>$100/month)
                if monthly_cost > 100:
                    analysis['expensive_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': resource_type,
                        'department': department,
                        'monthly_cost': monthly_cost
                    })

            # Get attributes
            attrs = item.get('attributes', {})

            # Check for idle EC2 instances
            if resource_type == 'ec2_instance' and attrs.get('state') == 'stopped':
                launch_time = attrs.get('launch_time', '')
                if launch_time:
                    try:
                        launch_dt = datetime.fromisoformat(launch_time.rstrip('Z'))
                        if datetime.now(UTC) - launch_dt > timedelta(days=30):
                            analysis['idle_resources'].append({
                                'resource_id': item.get('resource_id'),
                                'type': 'EC2 Instance',
                                'state': 'Stopped for >30 days',
                                'department': department
                            })
                    except:
                        pass

            # Check for oversized resources
            if resource_type == 'ec2_instance':
                instance_type = attrs.get('instance_type', '')
                # Simple heuristic: flag large instances
                if any(size in instance_type for size in ['xlarge', '2xlarge', '4xlarge']):
                    analysis['oversized_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'EC2 Instance',
                        'instance_type': instance_type,
                        'department': department,
                        'recommendation': 'Review if smaller instance type would suffice'
                    })

            # Check for unencrypted resources
            if resource_type in ['rds_instance', 'rds_cluster']:
                if not attrs.get('storage_encrypted', True):  # Default to True to avoid false positives
                    analysis['unencrypted_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': resource_type,
                        'department': department
                    })

            if resource_type == 's3_bucket':
                if not attrs.get('encryption', True):
                    analysis['unencrypted_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 's3_bucket',
                        'department': department
                    })

                # Check for public access
                if attrs.get('public_access', False):
                    analysis['public_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'S3 Bucket',
                        'department': department
                    })

            # Lambda optimization
            if resource_type == 'lambda_function':
                invocations = attrs.get('invocations_30d', 0)
                if invocations == 0:
                    analysis['idle_resources'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'Lambda Function',
                        'state': 'No invocations in 30 days',
                        'department': department
                    })
                elif attrs.get('error_rate', 0) > 10:
                    analysis['optimization_opportunities'].append({
                        'resource_id': item.get('resource_id'),
                        'type': 'Lambda Function',
                        'issue': f"High error rate: {attrs.get('error_rate', 0):.1f}%",
                        'department': department
                    })

        # Generate optimization recommendations
        total_monthly_cost = sum(analysis['cost_by_type'].values())

        if len(analysis['idle_resources']) > 0:
            analysis['optimization_opportunities'].append({
                'category': 'Idle Resources',
                'count': len(analysis['idle_resources']),
                'recommendation': 'Review and terminate idle resources',
                'potential_savings': f"${len(analysis['idle_resources']) * 50:.2f}/month (estimated)"
            })

        if len(analysis['oversized_resources']) > 0:
            analysis['optimization_opportunities'].append({
                'category': 'Right-sizing',
                'count': len(analysis['oversized_resources']),
                'recommendation': 'Review oversized instances for right-sizing opportunities',
                'potential_savings': f"${total_monthly_cost * 0.15:.2f}/month (15% estimated)"
            })

        if len(analysis['unencrypted_resources']) > 0:
            analysis['optimization_opportunities'].append({
                'category': 'Security',
                'count': len(analysis['unencrypted_resources']),
                'recommendation': 'Enable encryption for data security',
                'potential_savings': 'N/A - Security improvement'
            })

        # Convert defaultdicts to regular dicts
        analysis['cost_by_type'] = dict(analysis['cost_by_type'])
        analysis['cost_by_department'] = dict(analysis['cost_by_department'])
        analysis['cost_by_region'] = dict(analysis['cost_by_region'])

        return analysis

    def export_to_csv(self, filename: str, filters: dict | None = None):
        """Export inventory to CSV file"""
        # Get data based on filters
        if filters:
            if 'resource_type' in filters:
                items = self.query_by_resource_type(filters['resource_type'])
            elif 'department' in filters:
                items = self.query_by_department(filters['department'])
            else:
                items = self.get_all_resources()
        else:
            items = self.get_all_resources()

        if not items:
            print("No items to export")
            return

        # Flatten the data for CSV export
        flattened_data = []

        for item in items:
            flat_item = {
                'resource_type': item.get('resource_type'),
                'resource_id': item.get('resource_id'),
                'account_id': item.get('account_id'),
                'account_name': item.get('account_name') or item.get('department'),
                'region': item.get('region'),
                'timestamp': item.get('timestamp'),
                'estimated_monthly_cost': item.get('estimated_monthly_cost', 0)
            }

            # Add selected attributes
            attrs = item.get('attributes', {})
            if item.get('resource_type') == 'ec2_instance':
                flat_item.update({
                    'instance_type': attrs.get('instance_type'),
                    'state': attrs.get('state'),
                    'platform': attrs.get('platform'),
                    'vpc_id': attrs.get('vpc_id')
                })
            elif item.get('resource_type') == 'rds_instance':
                flat_item.update({
                    'engine': attrs.get('engine'),
                    'instance_class': attrs.get('instance_class'),
                    'status': attrs.get('status'),
                    'storage_encrypted': attrs.get('storage_encrypted')
                })
            elif item.get('resource_type') == 's3_bucket':
                flat_item.update({
                    'size_gb': attrs.get('size_gb'),
                    'versioning': attrs.get('versioning'),
                    'encryption': attrs.get('encryption'),
                    'public_access': attrs.get('public_access')
                })
            elif item.get('resource_type') == 'lambda_function':
                flat_item.update({
                    'function_name': attrs.get('function_name'),
                    'runtime': attrs.get('runtime'),
                    'memory_size': attrs.get('memory_size'),
                    'invocations_30d': attrs.get('invocations_30d')
                })

            # Add tags
            tags = attrs.get('tags', {})
            flat_item['name'] = tags.get('Name', '')
            flat_item['environment'] = tags.get('Environment', tags.get('env', ''))
            flat_item['owner'] = tags.get('Owner', '')

            flattened_data.append(flat_item)

        # Create DataFrame and export to CSV
        df = pd.DataFrame(flattened_data)
        df.to_csv(filename, index=False)

        print(f"Exported {len(items)} items to {filename}")

    def export_cost_report(self, filename: str):
        """Export detailed cost report to CSV"""
        analysis = self.get_cost_analysis()
        all_items = self.get_all_resources()

        # Create cost report data
        report_data = []

        for item in all_items:
            monthly_cost = 0
            if 'estimated_monthly_cost' in item:
                monthly_cost = float(item['estimated_monthly_cost'])
            elif 'estimated_hourly_cost' in item:
                monthly_cost = float(item['estimated_hourly_cost']) * 730

            if monthly_cost > 0:
                attrs = item.get('attributes', {})
                report_data.append({
                    'Resource ID': item.get('resource_id'),
                    'Resource Type': item.get('resource_type'),
                    'Department': item.get('department') or item.get('account_name'),
                    'Account ID': item.get('account_id'),
                    'Region': item.get('region'),
                    'Monthly Cost': f"${monthly_cost:.2f}",
                    'Annual Cost': f"${monthly_cost * 12:.2f}",
                    'Instance Type/Class': attrs.get('instance_type') or attrs.get('instance_class', 'N/A'),
                    'State/Status': attrs.get('state') or attrs.get('status', 'active')
                })

        # Sort by monthly cost descending
        report_data.sort(key=lambda x: float(x['Monthly Cost'].replace('$', '')), reverse=True)

        # Write to CSV
        if report_data:
            df = pd.DataFrame(report_data)
            df.to_csv(filename, index=False)
            print(f"Cost report exported to {filename}")
        else:
            print("No cost data to export")

    def get_stale_resources(self, days: int = 90) -> list[dict]:
        """Find resources that haven't been updated recently"""
        all_items = self.get_all_resources()
        stale_resources = []
        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        for item in all_items:
            attrs = item.get('attributes', {})

            # Check last modified or launch time
            last_update = None
            if 'last_modified' in attrs:
                last_update = attrs['last_modified']
            elif 'launch_time' in attrs:
                last_update = attrs['launch_time']
            elif 'creation_date' in attrs:
                last_update = attrs['creation_date']
            elif 'create_time' in attrs:
                last_update = attrs['create_time']

            if last_update:
                try:
                    update_dt = datetime.fromisoformat(last_update.rstrip('Z'))
                    if update_dt.tzinfo is None:
                        update_dt = update_dt.replace(tzinfo=UTC)

                    if update_dt < cutoff_date:
                        stale_resources.append({
                            'resource_id': item.get('resource_id'),
                            'resource_type': item.get('resource_type'),
                            'department': item.get('department') or item.get('account_name'),
                            'last_update': last_update,
                            'age_days': (datetime.now(UTC) - update_dt).days
                        })
                except:
                    pass

        return stale_resources


@click.command()
@click.option('--action', type=click.Choice(['summary', 'cost', 'export', 'cost-report', 'stale', 'query', 'security']), default='summary')
@click.option('--resource-type', help='Filter by resource type')
@click.option('--department', help='Filter by department')
@click.option('--region', help='Filter by region')
@click.option('--output', help='Output file for exports')
@click.option('--days', default=90, help='Days threshold for stale resources')
@click.option('--format', type=click.Choice(['table', 'json', 'csv']), default='table')
def main(action, resource_type, department, region, output, days, format):
    """Query AWS Inventory with Enhanced Features"""
    query = InventoryQuery()

    if action == 'summary':
        summary = query.get_summary()

        print("\n" + "="*60)
        print("AWS INVENTORY SUMMARY")
        print("="*60)
        print(f"\nTotal Resources: {summary['total_resources']}")
        print(f"\nEstimated Monthly Cost: ${summary['total_estimated_cost']['monthly']:.2f}")
        print(f"Estimated Annual Cost: ${summary['total_estimated_cost']['monthly'] * 12:.2f}")

        print("\n" + "-"*30)
        print("Resources by Type:")
        print("-"*30)
        type_data = [(k, v, f"${query.get_cost_analysis()['cost_by_type'].get(k, 0):.2f}")
                     for k, v in sorted(summary['by_type'].items(), key=lambda x: x[1], reverse=True)]
        print(tabulate(type_data, headers=['Type', 'Count', 'Monthly Cost'], tablefmt='grid'))

        print("\n" + "-"*30)
        print("Resources by Department:")
        print("-"*30)
        dept_data = [(k, v, f"${query.get_cost_analysis()['cost_by_department'].get(k, 0):.2f}")
                     for k, v in sorted(summary['by_department'].items(), key=lambda x: x[1], reverse=True)]
        print(tabulate(dept_data, headers=['Department', 'Count', 'Monthly Cost'], tablefmt='grid'))

        print("\n" + "-"*30)
        print("Resources by Region:")
        print("-"*30)
        region_data = [(k, v) for k, v in sorted(summary['by_region'].items(), key=lambda x: x[1], reverse=True)[:10]]
        print(tabulate(region_data, headers=['Region', 'Count'], tablefmt='grid'))

    elif action == 'cost':
        analysis = query.get_cost_analysis()

        print("\n" + "="*60)
        print("COST ANALYSIS & OPTIMIZATION")
        print("="*60)

        # Cost breakdown
        print("\nCost by Resource Type:")
        cost_type_data = [(k, f"${v:.2f}", f"{v/sum(analysis['cost_by_type'].values())*100:.1f}%")
                          for k, v in sorted(analysis['cost_by_type'].items(), key=lambda x: x[1], reverse=True)]
        print(tabulate(cost_type_data, headers=['Type', 'Monthly Cost', '% of Total'], tablefmt='grid'))

        # Top expensive resources
        if analysis['expensive_resources']:
            print("\n" + "-"*30)
            print(f"Top Expensive Resources (>${100}/month):")
            print("-"*30)
            exp_data = [(r['resource_id'][:40], r['type'], r['department'], f"${r['monthly_cost']:.2f}")
                        for r in sorted(analysis['expensive_resources'], key=lambda x: x['monthly_cost'], reverse=True)[:10]]
            print(tabulate(exp_data, headers=['Resource ID', 'Type', 'Dept', 'Monthly Cost'], tablefmt='grid'))

        # Optimization opportunities
        if analysis['optimization_opportunities']:
            print("\n" + "-"*30)
            print("Optimization Opportunities:")
            print("-"*30)
            for opp in analysis['optimization_opportunities']:
                print(f"\n• {opp.get('category', 'General')}:")
                print(f"  - Count: {opp.get('count', 'N/A')}")
                print(f"  - Recommendation: {opp.get('recommendation')}")
                print(f"  - Potential Savings: {opp.get('potential_savings')}")

    elif action == 'security':
        analysis = query.get_cost_analysis()

        print("\n" + "="*60)
        print("SECURITY COMPLIANCE CHECK")
        print("="*60)

        # Unencrypted resources
        if analysis['unencrypted_resources']:
            print(f"\n• Unencrypted Resources: {len(analysis['unencrypted_resources'])}")
            for r in analysis['unencrypted_resources'][:5]:
                print(f"  - {r['resource_id']} ({r['type']}) - {r['department']}")

        if analysis['public_resources']:
            print(f"\n• Public Resources: {len(analysis['public_resources'])}")
            for r in analysis['public_resources'][:5]:
                print(f"  - {r['resource_id']} ({r['type']}) - {r['department']}")

    elif action == 'export':
        if not output:
            output = f"inventory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filters = {}
        if resource_type:
            filters['resource_type'] = resource_type
        if department:
            filters['department'] = department

        query.export_to_csv(output, filters)

    elif action == 'cost-report':
        if not output:
            output = f"cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        query.export_cost_report(output)

    elif action == 'stale':
        stale = query.get_stale_resources(days)
        if stale:
            print(f"\nFound {len(stale)} resources older than {days} days:")
            stale_data = [(r['resource_id'][:40], r['resource_type'], r['department'], f"{r['age_days']} days")
                          for r in sorted(stale, key=lambda x: x['age_days'], reverse=True)[:20]]
            print(tabulate(stale_data, headers=['Resource ID', 'Type', 'Department', 'Age'], tablefmt='grid'))
        else:
            print(f"No resources older than {days} days found")

    elif action == 'query':
        # Custom query based on filters
        if resource_type:
            items = query.query_by_resource_type(resource_type)
        elif department:
            items = query.query_by_department(department)
        else:
            print("Please specify --resource-type or --department for query")
            return

        if format == 'json':
            print(json.dumps(items, indent=2, default=str))
        elif format == 'csv' and output:
            query.export_to_csv(output, {'resource_type': resource_type} if resource_type else {'department': department})
        else:
            # Table format
            if items:
                # Show first few items in table format
                table_data = []
                for item in items[:20]:
                    attrs = item.get('attributes', {})
                    state = (
                        item.get('state')
                        or item.get('status')
                        or attrs.get('state')
                        or attrs.get('status', 'active')
                    )
                    table_data.append([
                        item.get('resource_id', '')[:40],
                        item.get('resource_type', ''),
                        item.get('department') or item.get('account_name', ''),
                        item.get('region', ''),
                        state
                    ])
                print(tabulate(table_data, headers=['Resource ID', 'Type', 'Dept', 'Region', 'State'], tablefmt='grid'))
                if len(items) > 20:
                    print(f"\n... and {len(items) - 20} more resources")
            else:
                print("No resources found matching criteria")


if __name__ == '__main__':
    main()
