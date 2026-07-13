# Building an autonomous data quality response agent using AWS Glue Data Quality and Amazon Bedrock AgentCore

When an AWS Glue Data Quality rule fails in your S3 data lake, someone has to investigate. They check which columns are affected, review historical patterns, decide whether to quarantine the bad partition or wait for a re-run, and then document what they did for audit. This triage loop is manual, slow, and difficult to reproduce consistently across a team. A single quality failure can take 30 minutes of human attention before downstream consumers even know there is a problem.

[AWS Glue Data Quality](https://docs.aws.amazon.com/glue/latest/dg/glue-data-quality.html) solves the detection side: you define rules in the Data Quality Definition Language (DQDL), attach them to your Glue Data Catalog tables, and Glue evaluates completeness, freshness, distribution bounds, and schema stability automatically. But detection is only half the problem. Once Glue DQ tells you something is wrong, you still need to decide what to do about it.

In this post, we show you how to build an autonomous response agent that receives Glue DQ failure events, diagnoses root causes using LLM reasoning, quarantines bad records, notifies pipeline owners, and logs every decision to an auditable trail. The agent runs on [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html) and uses [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) foundation models for diagnosis. You define the detection rules in Glue DQ; the agent handles everything after.

## Solution overview

The diagram below illustrates the solution architecture.

<!-- Architecture diagram: upload to blog CMS. Alt text below. -->
![Architecture diagram showing data flowing from S3 through Glue DQ evaluation, to EventBridge, to a Lambda bridge function, to the Bedrock AgentCore agent, which then writes to S3 quarantine, DynamoDB audit tables, and SNS notifications](images/architecture-diagram.png)

The architecture separates detection from response across three phases:

**Detection** — Data lands in [Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) as Parquet files with Hive-style partitioning. [AWS Glue Data Quality](https://docs.aws.amazon.com/glue/latest/dg/glue-data-quality.html) evaluates a DQDL ruleset against each partition, checking completeness, freshness, distribution bounds, and schema existence.

**Routing** — When rules fail, Glue DQ emits an [Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html) event with state FAILED. An EventBridge rule matches the failure and invokes an [AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html) bridge function. The Lambda function fetches the full evaluation results from the Glue DQ API, normalizes them into a structured payload, and invokes the agent.

**Response** — The agent on [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html) parses the violations and takes action. It calls [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html) (Claude Haiku 4.5) to diagnose each root cause. Based on the diagnosis, it quarantines bad records via [Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/what-is.html) UNLOAD to an isolated S3 zone, sends severity-based alerts through [Amazon SNS](https://docs.aws.amazon.com/sns/latest/dg/welcome.html), logs every decision to [Amazon DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html), and emits metrics to [Amazon CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html).

The agent has five tools:

| Tool | Purpose |
|------|---------|
| `parse_dq_event` | Normalize the Glue DQ event into structured violations with severity classification |
| `diagnose_issue` | Call Bedrock with violation details and historical context for root cause analysis |
| `quarantine_records` | Run Athena UNLOAD to isolate bad records in a quarantine S3 zone with lineage tracking |
| `notify_owner` | Publish an SNS alert with severity, diagnosis, and recommended next steps |
| `log_decision` | Write every decision (what, why, outcome) to DynamoDB for audit |

## Walkthrough

This section walks you through deploying the complete solution: infrastructure, Glue DQ ruleset, agent, and a test of the end-to-end flow.

### Prerequisites

Before you begin, check that you have:

- An AWS account with administrative access
- [Python 3.11+](https://www.python.org/downloads/) installed
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager installed
- [Node.js 18+](https://nodejs.org/) and [AWS CDK v2](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html) installed (`npm install -g aws-cdk`)
- [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and configured with credentials
- The [agentcore CLI](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-get-started.html) installed
- Amazon Bedrock model access enabled for Claude Haiku 4.5 in us-east-1 (enable via the [Bedrock console model access page](https://console.aws.amazon.com/bedrock/home#/modelaccess))

### Step 1: Clone the repository and install dependencies

Start by cloning the sample repository and installing Python and Node.js dependencies.

```bash
git clone https://github.com/aws-samples/sample-agentic-data-quality-pipeline.git
cd sample-agentic-data-quality-pipeline
uv sync --all-extras
cd dashboard/ui && npm install && cd ../..
```

The repository contains the agent code, CDK infrastructure, a React dashboard, and sample data scripts.

### Step 2: Deploy the infrastructure

The solution uses four AWS CDK stacks: one for the data lake (Amazon S3, AWS Glue, Amazon Athena), one for observability (Amazon DynamoDB tables, Amazon CloudWatch alarms), one for notifications (Amazon SNS), and one for the Glue DQ integration (ruleset, Amazon EventBridge rule, AWS Lambda bridge).

Bootstrap CDK in your account if you haven't already, then deploy the three base stacks. (The fourth stack, the Glue DQ integration, needs the AgentCore runtime ID, so you deploy it in Step 4 after the agent exists.)

```bash
cd cdk
uv run --extra cdk -- npx cdk bootstrap aws://$(aws sts get-caller-identity --query Account --output text)/us-east-1
uv run --extra cdk -- npx cdk deploy DqAgentDataLake DqAgentObservability DqAgentNotification --require-approval never
cd ..
```

After deployment completes, the stack outputs include the S3 bucket name, SNS topic ARN, and Athena workgroup name. The Glue DQ ruleset (deployed in Step 4) contains these DQDL rules:

```
Rules = [
    Completeness "tpep_pickup_datetime" >= 0.98,
    Completeness "tpep_dropoff_datetime" >= 0.98,
    Completeness "passenger_count" >= 0.70,
    Completeness "trip_distance" >= 0.98,
    Completeness "fare_amount" >= 0.98,
    RowCount > 100000,
    Mean "fare_amount" between 5 and 100,
    Mean "trip_distance" between 0.5 and 50,
    ColumnExists "tpep_pickup_datetime",
    ColumnExists "tpep_dropoff_datetime",
    ColumnExists "passenger_count",
    ColumnExists "fare_amount",
    ColumnExists "trip_distance"
]
```

These rules encode the same quality dimensions a human would check: are required fields populated, is the row volume sane, are value distributions where they should be, and do critical columns exist. The thresholds are calibrated to the real dataset — NYC TLC data has roughly 25% organically null `passenger_count` values, so the completeness threshold for that column is 0.70 rather than a generic 0.98. Deriving thresholds from your data's actual baseline, rather than aspirational defaults, is what keeps a detection layer from crying wolf.

### Step 3: Load sample data into the data lake

Download three months of NYC TLC Yellow Taxi trip data (publicly available Parquet files, approximately 150 MB) and upload them to the S3 bucket with Hive-style partitioning.

```bash
BUCKET="dq-agent-demo-$(aws sts get-caller-identity --query Account --output text)"

uv run python data/download_data.py --start-year 2025 --start-month 7 --num-months 3
uv run python data/upload_to_s3.py --source data/raw --bucket $BUCKET --prefix raw/yellow_taxi
```

The upload script registers each partition in the Glue Data Catalog automatically, so Athena and Glue DQ can query the data immediately. (A CDK-defined table starts with zero partitions — without registration, an evaluation run would scan an empty dataset and pass vacuously.)

### Step 4: Deploy the agent to Bedrock AgentCore

Build the agent with the [Strands Agents SDK](https://github.com/strands-agents/sdk-python), an open-source Python framework for building tool-using agents on Amazon Bedrock. Configure and deploy it to AgentCore with these commands. The deploy script builds a container image via CodeBuild and registers it as an AgentCore runtime.

```bash
cd agent
agentcore configure --entrypoint agent.py --name dq_agent \
  --requirements-file requirements.txt --region us-east-1 \
  --protocol HTTP --non-interactive
bash ac_deploy.sh
cd ..
```

After deployment, the CLI outputs the agent ARN. Grant the AgentCore runtime role the permissions it needs to access DynamoDB, Athena, S3, Bedrock, SNS, and CloudWatch.

```bash
ROLE_NAME=$(aws iam list-roles --query "Roles[?contains(RoleName,'AgentCoreSDKRuntime')].RoleName" --output text)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name DqAgentDataAccess \
  --policy-document "{
  \"Version\":\"2012-10-17\",
  \"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:PutItem\",\"dynamodb:GetItem\",\"dynamodb:Query\",\"dynamodb:Scan\"],\"Resource\":\"arn:aws:dynamodb:us-east-1:${ACCOUNT_ID}:table/*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"athena:StartQueryExecution\",\"athena:GetQueryExecution\",\"athena:GetQueryResults\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\",\"s3:GetBucketLocation\"],\"Resource\":[\"arn:aws:s3:::dq-agent-demo-${ACCOUNT_ID}\",\"arn:aws:s3:::dq-agent-demo-${ACCOUNT_ID}/*\"]},
    {\"Effect\":\"Allow\",\"Action\":[\"glue:GetTable\",\"glue:GetPartitions\",\"glue:GetDatabase\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"bedrock:InvokeModel\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"sns:Publish\",\"sns:ListTopics\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":[\"cloudwatch:PutMetricData\"],\"Resource\":\"*\"}
  ]
}"
```

Now that the agent runtime exists, deploy the fourth stack — the Glue DQ ruleset, the EventBridge rule, and the Lambda bridge — passing the runtime ID from the `agentcore launch` output (the suffix of the agent ARN, e.g. `dq_agent-XXXXXXXXXX`):

```bash
cd cdk
uv run --extra cdk -- npx cdk deploy DqAgentGlueDq \
  -c agentcore_agent_id=<your-runtime-id> --require-approval never
cd ..
```

### Step 5: Run a baseline evaluation

Trigger a Glue DQ evaluation on a clean partition to verify the detection layer and establish a passing baseline. The `CloudWatchMetricsEnabled` option is required — Glue DQ only publishes EventBridge events for runs that have it enabled (the console sets it by default, but API-started runs must pass it explicitly).

```bash
aws glue start-data-quality-ruleset-evaluation-run \
  --data-source '{"GlueTable":{"DatabaseName":"dq_agent_demo","TableName":"raw_yellow_taxi","AdditionalOptions":{"pushDownPredicate":"year='\''2025'\'' AND month='\''08'\''"}}}' \
  --role "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/dq-agent-glue-role" \
  --ruleset-names "dq-agent-ruleset" \
  --additional-run-options '{"CloudWatchMetricsEnabled":true}' \
  --region us-east-1
```

The evaluation takes 2-3 minutes and all 13 rules pass. Glue DQ still emits an EventBridge event, and the Lambda bridge receives it, fetches the full result, finds zero failed rules, and skips the agent — you can confirm in the function's CloudWatch logs:

```bash
aws logs tail /aws/lambda/dq-agent-event-bridge --since 10m --region us-east-1
```

The log shows the received event and the line `No failed rules, skipping agent invocation`. The response layer only spends agent (and LLM) cycles when detection actually finds something.

### Step 6: Inject chaos and observe the agent response

The repository includes a chaos injector that introduces controlled quality issues (null spikes, fare and distance outliers, duplicates, format violations) into the Parquet data. This simulates real upstream data corruption. The injector preserves the parquet physical schema — pandas silently upcasts integer columns to float when nulls are injected, which would otherwise make the partition unreadable to both Athena and Glue DQ.

```bash
BUCKET="dq-agent-demo-$(aws sts get-caller-identity --query Account --output text)"

uv run python data/chaos_injector.py \
  --input data/raw/yellow_tripdata_2025-09.parquet \
  --output data/chaos/yellow_tripdata_2025-09.parquet \
  --config data/chaos_config.yaml

uv run python data/upload_to_s3.py \
  --file data/chaos/yellow_tripdata_2025-09.parquet \
  --bucket $BUCKET --prefix raw/yellow_taxi --overwrite
```

Now trigger another Glue DQ evaluation on the corrupted partition.

```bash
aws glue start-data-quality-ruleset-evaluation-run \
  --data-source '{"GlueTable":{"DatabaseName":"dq_agent_demo","TableName":"raw_yellow_taxi","AdditionalOptions":{"pushDownPredicate":"year='\''2025'\'' AND month='\''09'\''"}}}' \
  --role "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/dq-agent-glue-role" \
  --ruleset-names "dq-agent-ruleset" \
  --additional-run-options '{"CloudWatchMetricsEnabled":true}' \
  --region us-east-1
```

This time five rules fail: three completeness rules (`passenger_count` drops to 64%, `fare_amount` to 92%, `trip_distance` to 97%) and both distribution rules (the mean fare jumps from ~$19 to over $800 because of injected outliers). The EventBridge event fires, the Lambda bridge fetches the full evaluation result, recovers the partition scope from the run's pushdown predicate, and invokes the agent. The agent diagnoses each violation independently, quarantines records with null passenger counts and invalid fare amounts, sends a critical-severity SNS notification to the pipeline owner, and logs every decision. Check the audit trail:

```bash
aws dynamodb scan --table-name agent-decisions --region us-east-1 \
  --query 'Items[*].{Type:decision_type.S,Reasoning:reasoning.S}' \
  --output table
```

The output contains entries for `diagnosis_complete`, `remediation_executed`, and `notification_sent` with reasoning that references the specific quality dimensions that failed.

## How the agent reasons about failures

The agent's system prompt defines a structured workflow: RECEIVE, DIAGNOSE, ACT, LOG. When a Glue DQ failure arrives, the agent does not simply forward the alert. It makes a separate Bedrock LLM call for each violation, providing the specific failure metrics and historical context from previous evaluations stored in DynamoDB. This architecture allows the agent to handle multiple violations in a single partition, diagnosing each one independently and then correlating the results to decide whether the root cause is shared.

The diagnosis prompt asks the model to determine three things: what likely caused the issue (probable cause), how confident it is (HIGH, MEDIUM, LOW), and what action to take. The available actions are `quarantine_and_notify` (isolate bad records and alert the owner), `notify_only` (alert without quarantine), or `auto_resolve` (log as transient and take no further action). The separation between the orchestrating agent and the diagnostic call makes each diagnosis focused, auditable, and reproducible. To understand why the agent quarantined a specific partition, retrieve the exact prompt and response that informed that decision.

For example, when the agent receives a completeness violation showing 64% completeness on `passenger_count` — against a 70% threshold that was already calibrated for the dataset's ~75% organic baseline (certain NYC taxi vendors simply do not report passenger counts) — the diagnostic model can reason that a drop below an already-lenient threshold signals new upstream corruption rather than the known reporting gap. With historical context from DynamoDB showing prior evaluations passing, the recommendation is quarantine_and_notify with HIGH confidence. The same violation against a naive 98% threshold would be indistinguishable from the organic pattern.

In contrast, a distribution violation showing fare amounts of -$1,591 triggers a quarantine_and_notify recommendation. Negative fares are clearly invalid regardless of context. The agent isolates these records immediately before downstream analytics ingest them, and the pipeline owner receives a critical-severity notification with the diagnosis and the S3 path where quarantined records are stored.

When multiple violations share a common root cause (for example, a single corrupted upstream export causing null spikes in several columns at once), the agent batches related issues before acting. The system prompt instructs it to diagnose all violations in a partition before deciding on remediation, so that one upstream bug does not trigger five independent quarantine operations when one coordinated response is more appropriate.

## Quarantine zone design

Bad records are isolated in a dedicated quarantine prefix within the same S3 bucket, organized by table, partition, and issue ID.

```
s3://dq-agent-demo-<account>/quarantine/raw_yellow_taxi/year=2025/month=09/issue_id=<uuid>/<run>/
```

The agent uses Athena UNLOAD to write matching records to this path in Parquet format. The DynamoDB `remediation-history` table tracks every quarantine action: which records were moved, the SQL filter condition used, the quality score before and after, and a reference back to the Glue DQ evaluation ID that triggered the action. Any quarantine traces back to the specific rule failure that caused it.

Records in the quarantine zone have a 90-day S3 lifecycle rule. If the issue is resolved and the records need to be recovered, the lineage in DynamoDB provides exactly which run produced them and what filter was applied.

## Audit trail

Every agent decision writes to the `agent-decisions` DynamoDB table with a decision type (violation_detected, diagnosis_complete, remediation_executed, notification_sent), the agent's reasoning in natural language, the action taken, and the outcome. The audit trail answers three questions for any remediation: what happened, why did the agent take that action, and what was the result.

The table below shows a sample audit trail for a single evaluation that detected fare amount outliers.

| Timestamp | Decision type | Reasoning | Action | Outcome |
|-----------|--------------|-----------|--------|---------|
| T+0s | violation_detected | 5 rules failed: three completeness rules and two distribution (Mean) rules | Flagged for diagnosis | CRITICAL: 5 violations |
| T+3s | diagnosis_complete | Fare outliers caused by upstream vendor submitting negative adjustments as trip records | Quarantine recommended (HIGH confidence) | quarantine_and_notify |
| T+15s | remediation_executed | Quarantined 133,451 records matching fare_amount < -100 OR fare_amount > 500 | Athena UNLOAD to quarantine zone | Score: 45 → 78 |
| T+16s | notification_sent | Critical alert with diagnosis and quarantine path | SNS publish (critical) | Delivered |

The audit trail serves two purposes. First, it provides accountability. When a downstream consumer asks why their partition was quarantined, show them the exact chain from detection through remediation with the agent's reasoning at each step. Second, it enables improvement. By reviewing the agent's reasoning across multiple evaluations, identify patterns that should become new Glue DQ rules, pipeline validation checks, or adjustments to the agent's system prompt.

## Observability

The agent emits custom Amazon CloudWatch metrics for every action it takes: overall quality scores, anomaly counts by severity, remediation actions by type, and tool call durations. These feed into a CloudWatch dashboard that provides a real-time view of data quality health across your lake, alongside alarms that page when quality scores drop below thresholds or anomaly counts spike.

On AgentCore, OpenTelemetry traces every tool call, LLM invocation, and agent reasoning step. Each trace spans the full response chain from the moment the agent receives the Glue DQ event to the final log_decision write. The traces show not just that the agent quarantined records, but how long the diagnosis took, which Bedrock model was called, how many tokens were consumed, and whether any tool calls retried. The traces flow to AWS X-Ray through the ADOT collector that AgentCore provides automatically.

## Clean up

To avoid incurring future charges, delete the resources created during this walkthrough.

```bash
# Destroy the AgentCore agent
cd agent
agentcore destroy --agent dq_agent
cd ..

# Destroy all CDK stacks (the runtime ID context is needed for synth even on destroy)
cd cdk
uv run --extra cdk -- npx cdk destroy --all --force -c agentcore_agent_id=<your-runtime-id>
cd ..
```

The S3 bucket has `autoDeleteObjects` enabled and empties automatically during stack deletion. DynamoDB tables use `RemovalPolicy.DESTROY` and delete with the stack.

## Conclusion

In this post, we showed you how to build an autonomous response layer that sits downstream of AWS Glue Data Quality. The agent receives quality failure events through Amazon EventBridge, diagnoses root causes using Amazon Bedrock, quarantines bad records to an isolated S3 zone, notifies pipeline owners with actionable context, and logs every decision for audit.

The key architectural decisions include:

- Glue DQ handles detection through DQDL rules; the agent handles response through LLM reasoning and automated actions
- Event-driven invocation means the agent only runs when violations occur, with no polling or wasted compute
- Each diagnosis is a separate, focused Bedrock call with violation-specific context, making decisions auditable and reproducible
- Quarantine zones in S3 maintain full lineage back to the triggering Glue DQ evaluation, enabling recovery when needed
- The DynamoDB audit trail answers what happened, why, and what resulted, for every action the agent takes

To get started, clone the [sample repository](https://github.com/aws-samples/sample-agentic-data-quality-pipeline) and follow the walkthrough steps. For more information about the services used in this solution, see these resources:

- [AWS Glue Data Quality documentation](https://docs.aws.amazon.com/glue/latest/dg/glue-data-quality.html)
- [Amazon Bedrock AgentCore documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [DQDL rule type reference](https://docs.aws.amazon.com/glue/latest/dg/dqdl.html)

## About the authors

### Keagan Mirazee

Keagan Mirazee is a Partner Solutions Architect at AWS. He works with technology partners to design and build solutions on AWS, with a focus on data analytics and AI/ML workloads.
