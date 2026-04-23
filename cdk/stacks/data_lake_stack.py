"""Data Lake stack — S3 bucket, Glue Catalog (database + tables), Athena workgroup."""

import aws_cdk as cdk
from aws_cdk import (
    RemovalPolicy,
    aws_athena as athena,
    aws_glue as glue,
    aws_s3 as s3,
)
from constructs import Construct

# Columns matching the real NYC TLC Yellow Taxi parquet schema (2024)
YELLOW_TAXI_COLUMNS = [
    {"name": "VendorID", "type": "int"},
    {"name": "tpep_pickup_datetime", "type": "timestamp"},
    {"name": "tpep_dropoff_datetime", "type": "timestamp"},
    {"name": "passenger_count", "type": "bigint"},
    {"name": "trip_distance", "type": "double"},
    {"name": "RatecodeID", "type": "bigint"},
    {"name": "store_and_fwd_flag", "type": "string"},
    {"name": "PULocationID", "type": "int"},
    {"name": "DOLocationID", "type": "int"},
    {"name": "payment_type", "type": "bigint"},
    {"name": "fare_amount", "type": "double"},
    {"name": "extra", "type": "double"},
    {"name": "mta_tax", "type": "double"},
    {"name": "tip_amount", "type": "double"},
    {"name": "tolls_amount", "type": "double"},
    {"name": "improvement_surcharge", "type": "double"},
    {"name": "total_amount", "type": "double"},
    {"name": "congestion_surcharge", "type": "double"},
    {"name": "Airport_fee", "type": "double"},
]

PARTITION_KEYS = [
    {"name": "year", "type": "string"},
    {"name": "month", "type": "string"},
]

DATABASE_NAME = "dq_agent_demo"


class DataLakeStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = cdk.Stack.of(self).account

        # --- S3 Bucket ---
        self.bucket = s3.Bucket(
            self,
            "DataLakeBucket",
            bucket_name=f"dq-agent-demo-{account_id}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="QuarantineCleanup",
                    prefix="quarantine/",
                    expiration=cdk.Duration.days(90),
                ),
                s3.LifecycleRule(
                    id="TransitionToIA",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=cdk.Duration.days(30),
                        )
                    ],
                ),
            ],
        )

        # --- Glue Database ---
        self.database = glue.CfnDatabase(
            self,
            "GlueDatabase",
            catalog_id=account_id,
            database_input=glue.CfnDatabase.DatabaseInputProperty(name=DATABASE_NAME),
        )

        # --- Glue Tables ---
        table_configs = [
            ("raw_yellow_taxi", "raw/yellow_taxi"),
            ("staging_yellow_taxi", "staging/yellow_taxi"),
            ("curated_yellow_taxi", "curated/yellow_taxi"),
            ("quarantine_yellow_taxi", "quarantine/yellow_taxi"),
        ]

        self.tables = {}
        for table_name, prefix in table_configs:
            table = glue.CfnTable(
                self,
                f"Table_{table_name}",
                catalog_id=account_id,
                database_name=DATABASE_NAME,
                table_input=glue.CfnTable.TableInputProperty(
                    name=table_name,
                    table_type="EXTERNAL_TABLE",
                    parameters={"classification": "parquet", "has_encrypted_data": "false"},
                    storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                        location=f"s3://{self.bucket.bucket_name}/{prefix}/",
                        input_format="org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                        output_format="org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                        serde_info=glue.CfnTable.SerdeInfoProperty(
                            serialization_library="org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                        ),
                        columns=[
                            glue.CfnTable.ColumnProperty(name=c["name"], type=c["type"])
                            for c in YELLOW_TAXI_COLUMNS
                        ],
                    ),
                    partition_keys=[
                        glue.CfnTable.ColumnProperty(name=p["name"], type=p["type"]) for p in PARTITION_KEYS
                    ],
                ),
            )
            table.add_dependency(self.database)
            self.tables[table_name] = table

        # --- Athena Workgroup ---
        byte_limit = self.node.try_get_context("athena_byte_limit") or 104857600

        self.workgroup = athena.CfnWorkGroup(
            self,
            "AthenaWorkgroup",
            name="dq-agent-workgroup",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{self.bucket.bucket_name}/athena-results/",
                ),
                bytes_scanned_cutoff_per_query=int(byte_limit),
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True,
            ),
        )

        # --- Outputs ---
        cdk.CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        cdk.CfnOutput(self, "BucketArn", value=self.bucket.bucket_arn)
        cdk.CfnOutput(self, "DatabaseName", value=DATABASE_NAME)
        cdk.CfnOutput(self, "WorkgroupName", value=self.workgroup.name)
