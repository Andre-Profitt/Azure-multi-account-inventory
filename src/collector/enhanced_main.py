import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from decimal import Decimal

import boto3
import click
from botocore.exceptions import ClientError
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.sql import SqlManagementClient
from azure.mgmt.core.tools import parse_resource_id
from azure.data.tables import TableServiceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AWSInventoryCollector:
    """Enhanced AWS Inventory Collector with cost estimation and additional resource types"""

    def __init__(self, table_name: str = 'aws-inventory'):
        """Initialize the collector"""
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
        self.accounts = {}
        self.failed_collections = []
        self.excluded_regions = []
        self.resource_types = ['ec2', 'rds', 's3', 'lambda']
        self.external_id = os.environ.get('EXTERNAL_ID', 'inventory-collector')

        # Cost estimation (simplified, per hour)
        self.cost_estimates = {
            'ec2': {
                't2.micro': 0.0116, 't2.small': 0.023, 't2.medium': 0.0464,
                't3.micro': 0.0104, 't3.small': 0.0208, 't3.medium': 0.0416,
                'm5.large': 0.096, 'm5.xlarge': 0.192, 'm5.2xlarge': 0.384,
                'default': 0.05  # fallback estimate
            },
            'rds': {
                'db.t2.micro': 0.017, 'db.t3.micro': 0.017, 'db.t3.small': 0.034,
                'db.m5.large': 0.171, 'db.m5.xlarge': 0.342,
                'default': 0.10  # fallback estimate
            },
            's3': {
                'standard': 0.023,  # per GB per month
                'standard_ia': 0.0125,
                'glacier': 0.004,
                'deep_archive': 0.00099
            },
            'lambda': {
                'requests': 0.0000002,  # per request
                'gb_seconds': 0.0000166667  # per GB-second
            }
        }

    def load_config(self, config_path: str):
        """Load account configuration from JSON file"""
        with open(config_path) as f:
            config = json.load(f)
            self.accounts = config.get('accounts', {})
            self.excluded_regions = config.get('excluded_regions', [])
            self.resource_types = config.get('resource_types', ['ec2', 'rds', 's3', 'lambda'])
            # Filter enabled accounts only
            self.accounts = {k: v for k, v in self.accounts.items() if v.get('enabled', True)}
            logger.info(f"Loaded {len(self.accounts)} active accounts from config")

    def assume_role(self, account_id: str, role_name: str = 'InventoryRole',
                    session_name: str = None) -> boto3.Session:
        """Assume role in target account with retry logic"""
        if not session_name:
            session_name = f'inventory-{datetime.now().strftime("%Y%m%d%H%M%S")}'

        role_arn = f'arn:aws:iam::{account_id}:role/{role_name}'

        max_retries = 3
        for attempt in range(max_retries):
            try:
                sts = boto3.client('sts')
                response = sts.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName=session_name,
                    ExternalId=self.external_id
                )

                return boto3.Session(
                    aws_access_key_id=response['Credentials']['AccessKeyId'],
                    aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                    aws_session_token=response['Credentials']['SessionToken']
                )
            except ClientError as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Failed to assume role, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to assume role after {max_retries} attempts: {e}")
                    raise

    def get_regions(self, session: boto3.Session) -> list[str]:
        """Get list of enabled regions minus excluded ones"""
        ec2 = session.client('ec2')
        try:
            response = ec2.describe_regions()
            regions = [region['RegionName'] for region in response['Regions']]
            # Filter out excluded regions
            return [r for r in regions if r not in self.excluded_regions]
        except Exception as e:
            logger.error(f"Failed to get regions: {e}")
            return ['us-east-1']  # fallback

    def estimate_ec2_cost(self, instance: dict) -> float:
        """Estimate EC2 instance cost per month"""
        instance_type = instance.get('InstanceType', 'unknown')
        state = instance.get('State', {}).get('Name', 'unknown')

        if state != 'running':
            return 0.0

        hourly_cost = self.cost_estimates['ec2'].get(
            instance_type,
            self.cost_estimates['ec2']['default']
        )
        return hourly_cost * 24 * 30  # Monthly cost

    def estimate_rds_cost(self, instance: dict) -> float:
        """Estimate RDS instance cost per month"""
        instance_class = instance.get('DBInstanceClass', 'unknown')
        status = instance.get('DBInstanceStatus', 'unknown')

        if status != 'available':
            return 0.0

        hourly_cost = self.cost_estimates['rds'].get(
            instance_class,
            self.cost_estimates['rds']['default']
        )
        return hourly_cost * 24 * 30  # Monthly cost

    def estimate_s3_cost(self, bucket_metrics: dict) -> float:
        """Estimate S3 bucket cost per month"""
        size_gb = bucket_metrics.get('size_bytes', 0) / (1024 ** 3)
        storage_class = bucket_metrics.get('storage_class', 'standard')

        gb_month_cost = self.cost_estimates['s3'].get(
            storage_class.lower(),
            self.cost_estimates['s3']['standard']
        )
        return size_gb * gb_month_cost

    def collect_ec2_instances(self, session: boto3.Session, region: str,
                            account_id: str, account_name: str) -> list[dict]:
        """Collect EC2 instances from a region"""
        resources = []

        try:
            ec2 = session.client('ec2', region_name=region)
            paginator = ec2.get_paginator('describe_instances')

            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        resource = {
                            'resource_type': 'ec2_instance',
                            'resource_id': instance['InstanceId'],
                            'account_id': account_id,
                            'account_name': account_name,
                            'region': region,
                            'timestamp': datetime.now(UTC).isoformat(),
                            'attributes': {
                                'instance_type': instance.get('InstanceType'),
                                'state': instance.get('State', {}).get('Name'),
                                'launch_time': instance.get('LaunchTime', '').isoformat() if instance.get('LaunchTime') else None,
                                'platform': instance.get('Platform', 'linux'),
                                'vpc_id': instance.get('VpcId'),
                                'subnet_id': instance.get('SubnetId'),
                                'public_ip': instance.get('PublicIpAddress'),
                                'private_ip': instance.get('PrivateIpAddress'),
                                'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])},
                                'security_groups': [sg['GroupId'] for sg in instance.get('SecurityGroups', [])],
                                'iam_instance_profile': instance.get('IamInstanceProfile', {}).get('Arn')
                            },
                            'estimated_monthly_cost': self.estimate_ec2_cost(instance)
                        }
                        resources.append(resource)

            logger.info(f"Collected {len(resources)} EC2 instances from {account_name}/{region}")

        except Exception as e:
            logger.error(f"Error collecting EC2 instances from {account_name}/{region}: {e}")

        return resources

    def collect_rds_instances(self, session: boto3.Session, region: str,
                            account_id: str, account_name: str) -> list[dict]:
        """Collect RDS instances and clusters from a region"""
        resources = []

        try:
            rds = session.client('rds', region_name=region)

            # Collect DB instances
            paginator = rds.get_paginator('describe_db_instances')
            for page in paginator.paginate():
                for instance in page['DBInstances']:
                    resource = {
                        'resource_type': 'rds_instance',
                        'resource_id': instance['DBInstanceIdentifier'],
                        'account_id': account_id,
                        'account_name': account_name,
                        'region': region,
                        'timestamp': datetime.now(UTC).isoformat(),
                        'attributes': {
                            'engine': instance.get('Engine'),
                            'engine_version': instance.get('EngineVersion'),
                            'instance_class': instance.get('DBInstanceClass'),
                            'status': instance.get('DBInstanceStatus'),
                            'allocated_storage': instance.get('AllocatedStorage'),
                            'storage_encrypted': instance.get('StorageEncrypted', False),
                            'multi_az': instance.get('MultiAZ', False),
                            'vpc_id': instance.get('DBSubnetGroup', {}).get('VpcId'),
                            'create_time': instance.get('InstanceCreateTime', '').isoformat() if instance.get('InstanceCreateTime') else None,
                            'backup_retention': instance.get('BackupRetentionPeriod'),
                            'tags': {tag['Key']: tag['Value'] for tag in instance.get('TagList', [])}
                        },
                        'estimated_monthly_cost': self.estimate_rds_cost(instance)
                    }
                    resources.append(resource)

            # Collect DB clusters
            try:
                paginator = rds.get_paginator('describe_db_clusters')
                for page in paginator.paginate():
                    for cluster in page['DBClusters']:
                        resource = {
                            'resource_type': 'rds_cluster',
                            'resource_id': cluster['DBClusterIdentifier'],
                            'account_id': account_id,
                            'account_name': account_name,
                            'region': region,
                            'timestamp': datetime.now(UTC).isoformat(),
                            'attributes': {
                                'engine': cluster.get('Engine'),
                                'engine_version': cluster.get('EngineVersion'),
                                'status': cluster.get('Status'),
                                'storage_encrypted': cluster.get('StorageEncrypted', False),
                                'multi_az': cluster.get('MultiAZ', False),
                                'cluster_members': len(cluster.get('DBClusterMembers', [])),
                                'backup_retention': cluster.get('BackupRetentionPeriod'),
                                'tags': {tag['Key']: tag['Value'] for tag in cluster.get('TagList', [])}
                            }
                        }
                        resources.append(resource)
            except Exception as e:
                logger.warning(f"Error collecting RDS clusters: {e}")

            logger.info(f"Collected {len(resources)} RDS resources from {account_name}/{region}")

        except Exception as e:
            logger.error(f"Error collecting RDS instances from {account_name}/{region}: {e}")

        return resources

    def collect_s3_buckets(self, session: boto3.Session, account_id: str,
                          account_name: str) -> list[dict]:
        """Collect S3 buckets (global service)"""
        resources = []

        try:
            s3 = session.client('s3')
            cloudwatch = session.client('cloudwatch', region_name='us-east-1')

            response = s3.list_buckets()

            for bucket in response['Buckets']:
                bucket_name = bucket['Name']
                bucket_info = {
                    'resource_type': 's3_bucket',
                    'resource_id': bucket_name,
                    'account_id': account_id,
                    'account_name': account_name,
                    'region': 'global',
                    'timestamp': datetime.now(UTC).isoformat(),
                    'attributes': {
                        'creation_date': bucket.get('CreationDate', '').isoformat() if bucket.get('CreationDate') else None,
                        'tags': {}
                    }
                }

                # Get bucket location
                try:
                    location_resp = s3.get_bucket_location(Bucket=bucket_name)
                    bucket_info['region'] = location_resp.get('LocationConstraint') or 'us-east-1'
                except Exception as e:
                    logger.warning(
                        "Error getting location for bucket %s: %s", bucket_name, e
                    )

                # Get bucket versioning
                try:
                    versioning = s3.get_bucket_versioning(Bucket=bucket_name)
                    bucket_info['attributes']['versioning'] = versioning.get('Status', 'Disabled')
                except Exception as e:
                    logger.warning(
                        "Error getting versioning for bucket %s: %s", bucket_name, e
                    )
                    bucket_info['attributes']['versioning'] = 'Unknown'

                # Get bucket encryption
                try:
                    encryption = s3.get_bucket_encryption(Bucket=bucket_name)
                    bucket_info['attributes']['encryption'] = True
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ServerSideEncryptionConfigurationNotFoundError':
                        bucket_info['attributes']['encryption'] = False
                    else:
                        bucket_info['attributes']['encryption'] = 'Unknown'

                # Get bucket size from CloudWatch
                try:
                    size_metric = cloudwatch.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='BucketSizeBytes',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'StandardStorage'}
                        ],
                        StartTime=datetime.now(UTC) - timedelta(days=1),
                        EndTime=datetime.now(UTC),
                        Period=86400,
                        Statistics=['Average']
                    )

                    if size_metric['Datapoints']:
                        size_bytes = size_metric['Datapoints'][0]['Average']
                        bucket_info['attributes']['size_bytes'] = size_bytes
                        bucket_info['attributes']['size_gb'] = round(size_bytes / (1024**3), 2)
                        bucket_info['estimated_monthly_cost'] = self.estimate_s3_cost({
                            'size_bytes': size_bytes,
                            'storage_class': 'standard'
                        })
                    else:
                        bucket_info['attributes']['size_bytes'] = 0
                        bucket_info['estimated_monthly_cost'] = 0
                except Exception as e:
                    logger.warning(
                        "Error getting size metrics for bucket %s: %s", bucket_name, e
                    )
                    bucket_info['attributes']['size_bytes'] = 0
                    bucket_info['estimated_monthly_cost'] = 0

                # Get object count
                try:
                    count_metrics = cloudwatch.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='NumberOfObjects',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
                        ],
                        StartTime=datetime.now(UTC) - timedelta(days=1),
                        EndTime=datetime.now(UTC),
                        Period=86400,
                        Statistics=['Average']
                    )
                    if count_metrics['Datapoints']:
                        bucket_info['attributes']['object_count'] = int(count_metrics['Datapoints'][0]['Average'])
                    else:
                        bucket_info['attributes']['object_count'] = 0
                except Exception as e:
                    logger.warning(
                        "Error getting object count for bucket %s: %s", bucket_name, e
                    )
                    bucket_info['attributes']['object_count'] = None

                # Get bucket tags
                try:
                    tags_resp = s3.get_bucket_tagging(Bucket=bucket_name)
                    bucket_info['attributes']['tags'] = {
                        tag['Key']: tag['Value'] for tag in tags_resp.get('TagSet', [])
                    }
                except ClientError as e:
                    if e.response['Error']['Code'] != 'NoSuchTagSet':
                        logger.warning(f"Error getting tags for bucket {bucket_name}: {e}")

                # Check public access
                try:
                    acl = s3.get_bucket_acl(Bucket=bucket_name)
                    public_access = any(
                        grant.get('Grantee', {}).get('Type') == 'Group' and
                        grant.get('Grantee', {}).get('URI', '').endswith('AllUsers')
                        for grant in acl.get('Grants', [])
                    )
                    bucket_info['attributes']['public_access'] = public_access
                except Exception as e:
                    logger.warning(
                        "Error getting ACL for bucket %s: %s", bucket_name, e
                    )
                    bucket_info['attributes']['public_access'] = 'Unknown'

                resources.append(bucket_info)

            logger.info(f"Collected {len(resources)} S3 buckets from {account_name}")

        except Exception as e:
            logger.error(f"Error collecting S3 buckets from {account_name}: {e}")

        return resources

    def collect_lambda_functions(self, session: boto3.Session, region: str,
                               account_id: str, account_name: str) -> list[dict]:
        """Collect Lambda functions from a region"""
        resources = []

        try:
            lambda_client = session.client('lambda', region_name=region)
            cloudwatch = session.client('cloudwatch', region_name=region)

            paginator = lambda_client.get_paginator('list_functions')

            for page in paginator.paginate():
                for function in page['Functions']:
                    function_name = function['FunctionName']

                    # Get invocation metrics
                    invocations = 0
                    errors = 0
                    try:
                        # Get invocation count for last 30 days
                        invocation_metric = cloudwatch.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Invocations',
                            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                            StartTime=datetime.now(UTC) - timedelta(days=30),
                            EndTime=datetime.now(UTC),
                            Period=2592000,  # 30 days
                            Statistics=['Sum']
                        )

                        if invocation_metric['Datapoints']:
                            invocations = int(invocation_metric['Datapoints'][0]['Sum'])

                        # Get error count
                        error_metric = cloudwatch.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName='Errors',
                            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                            StartTime=datetime.now(UTC) - timedelta(days=30),
                            EndTime=datetime.now(UTC),
                            Period=2592000,
                            Statistics=['Sum']
                        )

                        if error_metric['Datapoints']:
                            errors = int(error_metric['Datapoints'][0]['Sum'])
                    except Exception as e:
                        logger.warning(f"Error getting metrics for Lambda {function_name}: {e}")

                    # Estimate monthly cost
                    memory_mb = function.get('MemorySize', 128)
                    # Assume average duration of 100ms per invocation
                    gb_seconds = (memory_mb / 1024) * (invocations * 0.1)
                    monthly_cost = (invocations * self.cost_estimates['lambda']['requests'] +
                                  gb_seconds * self.cost_estimates['lambda']['gb_seconds'])

                    resource = {
                        'resource_type': 'lambda_function',
                        'resource_id': function['FunctionArn'],
                        'account_id': account_id,
                        'account_name': account_name,
                        'region': region,
                        'timestamp': datetime.now(UTC).isoformat(),
                        'attributes': {
                            'function_name': function_name,
                            'runtime': function.get('Runtime'),
                            'handler': function.get('Handler'),
                            'code_size': function.get('CodeSize'),
                            'memory_size': memory_mb,
                            'timeout': function.get('Timeout'),
                            'last_modified': function.get('LastModified'),
                            'description': function.get('Description', ''),
                            'role': function.get('Role'),
                            'invocations_30d': invocations,
                            'errors_30d': errors,
                            'error_rate': round((errors / invocations * 100), 2) if invocations > 0 else 0,
                            'tags': function.get('Tags', {})
                        },
                        'estimated_monthly_cost': round(monthly_cost, 2)
                    }
                    resources.append(resource)

            logger.info(f"Collected {len(resources)} Lambda functions from {account_name}/{region}")

        except Exception as e:
            logger.error(f"Error collecting Lambda functions from {account_name}/{region}: {e}")

        return resources

    def collect_account_inventory(self, account_name: str, account_info: dict) -> list[dict]:
        """Collect inventory from a single account with parallel region processing"""
        account_id = account_info['account_id']
        role_name = account_info.get('role_name', 'InventoryRole')

        logger.info(f"Collecting inventory from account: {account_name} ({account_id})")

        try:
            session = self.assume_role(account_id, role_name)
            regions = self.get_regions(session)

            all_resources = []

            # Collect S3 buckets (global service)
            if 's3' in self.resource_types:
                all_resources.extend(self.collect_s3_buckets(session, account_id, account_name))

            # Collect regional resources in parallel
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []

                for region in regions:
                    # EC2 instances
                    if 'ec2' in self.resource_types:
                        futures.append(
                            executor.submit(self.collect_ec2_instances, session, region, account_id, account_name)
                        )
                    # RDS instances
                    if 'rds' in self.resource_types:
                        futures.append(
                            executor.submit(self.collect_rds_instances, session, region, account_id, account_name)
                        )
                    # Lambda functions
                    if 'lambda' in self.resource_types:
                        futures.append(
                            executor.submit(self.collect_lambda_functions, session, region, account_id, account_name)
                        )

                # Collect results
                for future in as_completed(futures):
                    try:
                        resources = future.result()
                        all_resources.extend(resources)
                    except Exception as e:
                        logger.error(f"Error in parallel collection: {e}")

            logger.info(f"Collected {len(all_resources)} total resources from {account_name}")
            return all_resources

        except Exception as e:
            logger.error(f"Failed to collect inventory from {account_name}: {e}")
            self.failed_collections.append({
                'department': account_name,
                'account_id': account_id,
                'error': str(e)
            })
            return []

    def save_to_dynamodb(self, resources: list[dict]):
        """Save resources to DynamoDB with batching and proper type handling"""
        if not resources:
            return

        # Convert floats to Decimal for DynamoDB
        def convert_floats(obj):
            if isinstance(obj, float):
                return Decimal(str(obj))
            if isinstance(obj, dict):
                return {k: convert_floats(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert_floats(v) for v in obj]
            return obj

        # Batch write to DynamoDB
        with self.table.batch_writer() as batch:
            for resource in resources:
                # Create pk/sk pattern for better querying
                pk = f"{resource['resource_type']}#{resource['account_id']}#{resource.get('region', 'global')}#{resource['resource_id']}"
                sk = resource['timestamp']

                item = {
                    'pk': pk,
                    'sk': sk,
                    'resource_type': resource['resource_type'],
                    'department': resource.get('account_name', 'unknown'),
                    **convert_floats(resource)
                }

                batch.put_item(Item=item)

        logger.info(f"Saved {len(resources)} resources to DynamoDB")

    def collect_inventory(self) -> list[dict]:
        """Collect inventory from all configured accounts"""
        if not self.accounts:
            logger.error("No accounts configured")
            return []

        all_resources = []
        self.failed_collections = []  # Reset failed collections

        # Process accounts in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.collect_account_inventory, name, info): name
                for name, info in self.accounts.items()
            }

            for future in as_completed(futures):
                account_name = futures[future]
                try:
                    resources = future.result()
                    all_resources.extend(resources)
                except Exception as e:
                    logger.error(f"Failed to process account {account_name}: {e}")
                    self.failed_collections.append({
                        'department': account_name,
                        'account_id': self.accounts[account_name]['account_id'],
                        'error': str(e)
                    })

        # Save to DynamoDB
        self.save_to_dynamodb(all_resources)

        # Log summary of failed collections
        if self.failed_collections:
            logger.warning(f"Failed collections: {len(self.failed_collections)}")
            for failure in self.failed_collections:
                logger.warning(f"  - {failure['department']} ({failure['account_id']}): {failure['error']}")

        return all_resources


class AzureInventoryCollector:
    """Basic Azure Inventory Collector"""

    def __init__(self, subscription_id: str, table_url: str | None = None,
                 table_name: str | None = None):
        self.subscription_id = subscription_id
        self.credential = DefaultAzureCredential()
        self.compute_client = ComputeManagementClient(self.credential, subscription_id)
        self.sql_client = SqlManagementClient(self.credential, subscription_id)
        self.table_url = table_url or os.environ.get('AZURE_TABLE_URL')
        self.table_name = table_name or os.environ.get('AZURE_TABLE_NAME', 'inventory')

    def collect_virtual_machines(self) -> list[dict]:
        resources = []
        for vm in self.compute_client.virtual_machines.list_all():
            resources.append({
                'resource_type': 'vm',
                'resource_id': vm.id,
                'account_id': self.subscription_id,
                'region': vm.location,
                'timestamp': datetime.now(UTC).isoformat(),
                'attributes': {
                    'vm_size': getattr(vm.hardware_profile, 'vm_size', None),
                    'os_type': getattr(vm.storage_profile.os_disk, 'os_type', None).value if vm.storage_profile and vm.storage_profile.os_disk else None,
                    'tags': vm.tags or {}
                }
            })
        return resources

    def collect_sql_databases(self) -> list[dict]:
        """Collect SQL databases and infer the resource group from each ID.

        The Azure ``parse_resource_id`` helper is used to parse the database
        identifier and extract its ``resource_group``. If the ID cannot be
        parsed, the resource group defaults to ``'unknown'``. This allows the
        collector to gracefully handle unexpected ID formats without raising an
        exception.
        """
        resources = []
        for db in self.sql_client.databases.list_by_subscription():
            try:
                parsed = parse_resource_id(db.id or '')
                resource_group = parsed.get('resource_group', 'unknown')
            except Exception:
                resource_group = 'unknown'

            resources.append({
                'resource_type': 'sql_database',
                'resource_id': db.id,
                'account_id': self.subscription_id,
                'region': db.location,
                'timestamp': datetime.now(UTC).isoformat(),
                'attributes': {
                    'resource_group': resource_group,
                    'tags': db.tags or {}
                }
            })
        return resources

    def save_to_table(self, resources: list[dict]):
        """Persist collected resources to Azure Table Storage."""
        if not resources or not self.table_url:
            return

        service = TableServiceClient(endpoint=self.table_url, credential=self.credential)
        table = service.get_table_client(self.table_name)

        for resource in resources:
            entity = {
                'PartitionKey': resource.get('account_id', 'unknown'),
                'RowKey': resource.get('resource_id').replace('/', '_'),
                'resource_type': resource.get('resource_type'),
                'account_name': resource.get('account_name'),
                'region': resource.get('region'),
                'timestamp': resource.get('timestamp'),
                'estimated_monthly_cost': resource.get('estimated_monthly_cost', 0),
                'attributes': json.dumps(resource.get('attributes', {}))
            }
            table.upsert_entity(entity)

        logger.info(f"Saved {len(resources)} resources to Azure Table {self.table_name}")

    def collect_inventory(self) -> list[dict]:
        resources = self.collect_virtual_machines()
        self.save_to_table(resources)
        return resources


@click.command()
@click.option('--config', default='config/accounts.json', help='Config file path')
@click.option('--table', default='aws-inventory', help='DynamoDB table name')
@click.option('--dry-run', is_flag=True, help='Show what would be collected')
@click.option('--resource-types', help='Comma-separated resource types to collect (ec2,rds,s3,lambda)')
@click.option('--debug', is_flag=True, help='Enable debug logging')
def main(config, table, dry_run, resource_types, debug):
    """AWS Multi-Account Inventory Collector"""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if os.environ.get('CLOUD_PROVIDER') == 'azure':
        subscription_id = os.environ.get('AZURE_SUBSCRIPTION_ID')
        collector = AzureInventoryCollector(subscription_id)
    else:
        collector = AWSInventoryCollector(table_name=table)
    collector.load_config(config)

    if resource_types:
        collector.resource_types = resource_types.split(',')

    if dry_run:
        logger.info("DRY RUN - Would collect:")
        for dept, info in collector.accounts.items():
            logger.info(f"  {dept}: {info['account_id']}")
        logger.info(f"Resource types: {collector.resource_types}")
        logger.info(f"Excluded regions: {collector.excluded_regions}")
        return

    resources = collector.collect_inventory()

    # Print summary
    summary = {}
    total_cost = 0

    for resource in resources:
        resource_type = resource['resource_type']
        summary[resource_type] = summary.get(resource_type, 0) + 1
        total_cost += resource.get('estimated_monthly_cost', 0)

    print("\nInventory Summary:")
    print("-" * 50)
    for resource_type, count in sorted(summary.items()):
        print(f"{resource_type}: {count}")
    print("-" * 50)
    print(f"Total resources: {len(resources)}")
    print(f"Estimated monthly cost: ${total_cost:,.2f}")

    if collector.failed_collections:
        print(f"\nFailed collections: {len(collector.failed_collections)}")


if __name__ == '__main__':
    main()
