"""Observability stack — 4 DynamoDB tables for agent state."""

import aws_cdk as cdk
from aws_cdk import RemovalPolicy, aws_dynamodb as ddb
from constructs import Construct

TTL_ATTRIBUTE = "ttl"


class ObservabilityStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        table_defs = [
            ("quality-scan-results", "PK", "SK"),
            ("agent-decisions", "PK", "SK"),
            ("schema-baselines", "PK", "SK"),
            ("remediation-history", "PK", "SK"),
        ]

        self.tables = {}
        for name, pk, sk in table_defs:
            table = ddb.Table(
                self,
                name,
                table_name=name,
                partition_key=ddb.Attribute(name=pk, type=ddb.AttributeType.STRING),
                sort_key=ddb.Attribute(name=sk, type=ddb.AttributeType.STRING),
                billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
                removal_policy=RemovalPolicy.DESTROY,
                time_to_live_attribute=TTL_ATTRIBUTE if name != "schema-baselines" else None,
            )
            self.tables[name] = table
            cdk.CfnOutput(self, f"{name}-arn", value=table.table_arn)
