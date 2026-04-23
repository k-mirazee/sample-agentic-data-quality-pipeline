#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.data_lake_stack import DataLakeStack
from stacks.observability_stack import ObservabilityStack
from stacks.notification_stack import NotificationStack

app = cdk.App()

account = app.node.try_get_context("account") or "015331669295"
region = app.node.try_get_context("region") or "us-east-1"
env = cdk.Environment(account=account, region=region)

DataLakeStack(app, "DqAgentDataLake", env=env)
ObservabilityStack(app, "DqAgentObservability", env=env)
NotificationStack(app, "DqAgentNotification", env=env)

app.synth()
