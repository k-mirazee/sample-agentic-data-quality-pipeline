#!/usr/bin/env python3
import os

import aws_cdk as cdk
from stacks.data_lake_stack import DataLakeStack
from stacks.glue_dq_stack import GlueDqStack
from stacks.notification_stack import NotificationStack
from stacks.observability_stack import ObservabilityStack

app = cdk.App()

account = app.node.try_get_context("account") or os.environ.get("CDK_DEFAULT_ACCOUNT")
region = app.node.try_get_context("region") or os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

if not account:
    import boto3
    account = boto3.client("sts").get_caller_identity()["Account"]

env = cdk.Environment(account=account, region=region)

data_lake = DataLakeStack(app, "DqAgentDataLake", env=env)
ObservabilityStack(app, "DqAgentObservability", env=env)
NotificationStack(app, "DqAgentNotification", env=env)
glue_dq = GlueDqStack(app, "DqAgentGlueDq", env=env)
glue_dq.add_dependency(data_lake)

app.synth()
