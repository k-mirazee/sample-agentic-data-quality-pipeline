# Demo Guide

Step-by-step walkthrough for demonstrating the Data Quality Agent. Expected duration: 15–20 minutes. Expected cost: <$5.

## Prerequisites

- AWS account `015331669295` (or your own) with CDK deployed
- Bedrock model access enabled (Claude Haiku 4.5)
- NYC TLC data downloaded (at least 1 month)
- `uv`, `agentcore` CLI installed

## Step 1: Deploy Infrastructure

```bash
cd cdk
uv run --extra cdk -- npx cdk deploy --app "python3 app.py" --all --require-approval never
```

This creates: S3 bucket, Glue database + 4 tables, Athena workgroup, 4 DynamoDB tables, SNS topic, CloudWatch alarms + dashboard.

## Step 2: Download and Upload Clean Data

```bash
# Download 3 months of yellow taxi data (~150MB)
uv run python data/download_data.py --start-year 2024 --start-month 1 --num-months 3

# Upload to S3
uv run python data/upload_to_s3.py --source data/raw --bucket dq-agent-demo-<ACCOUNT_ID> --prefix raw/yellow_taxi
```

Add Glue partitions:
```bash
aws glue batch-create-partition --database-name dq_agent_demo --table-name raw_yellow_taxi \
  --partition-input-list '[{"Values":["2024","01"],"StorageDescriptor":{"Location":"s3://dq-agent-demo-<ACCOUNT_ID>/raw/yellow_taxi/year=2024/month=01/","InputFormat":"org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat","OutputFormat":"org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat","SerdeInfo":{"SerializationLibrary":"org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"},"Columns":[{"Name":"VendorID","Type":"int"},{"Name":"tpep_pickup_datetime","Type":"timestamp"},{"Name":"tpep_dropoff_datetime","Type":"timestamp"},{"Name":"passenger_count","Type":"bigint"},{"Name":"trip_distance","Type":"double"},{"Name":"RatecodeID","Type":"bigint"},{"Name":"store_and_fwd_flag","Type":"string"},{"Name":"PULocationID","Type":"int"},{"Name":"DOLocationID","Type":"int"},{"Name":"payment_type","Type":"bigint"},{"Name":"fare_amount","Type":"double"},{"Name":"extra","Type":"double"},{"Name":"mta_tax","Type":"double"},{"Name":"tip_amount","Type":"double"},{"Name":"tolls_amount","Type":"double"},{"Name":"improvement_surcharge","Type":"double"},{"Name":"total_amount","Type":"double"},{"Name":"congestion_surcharge","Type":"double"},{"Name":"Airport_fee","Type":"double"}]}}]'
```

## Step 3: Run Baseline Scan (Expect Warnings)

```bash
uv run python -m agent.agent --table raw_yellow_taxi --partition "year=2024/month=01"
```

**Expected result:** Score ~62.7/100 CRITICAL (freshness is stale since it's historical data), completeness WARNING (4.73% null passenger_count), distribution OK with minor outliers.

The agent will: scan → diagnose × 3 → attempt remediation → notify × 3 → log decisions.

## Step 4: Inject Chaos

```bash
# Generate corrupted data
uv run python data/chaos_injector.py --input data/raw --output data/chaos --config data/chaos_config.yaml

# Upload chaos data (overwrite clean)
uv run python data/upload_to_s3.py --source data/chaos --bucket dq-agent-demo-<ACCOUNT_ID> --prefix raw/yellow_taxi --overwrite
```

This injects: 15% null passenger_count, outlier fares (-$1000 to $50K), schema drift (fare_amount → fare_amt, Airport_fee dropped, VendorID → string), 5% duplicates, backdated timestamps, format violations.

## Step 5: Re-scan (Expect Critical Failures)

```bash
uv run python -m agent.agent --table raw_yellow_taxi --partition "year=2024/month=01"
```

**Expected result:** The schema type mismatch (VendorID int→string) will cause Athena queries to fail. The agent will pivot to `check_schema`, detect the drift, and flag CRITICAL.

## Step 6: Open Dashboard

```bash
PYTHONPATH=. uv run streamlit run dashboard/app.py
```

Walk through each page:
1. **Overview** — Quality score dropped, anomalies timeline, alarm status
2. **Scan Details** — Drill into violations per dimension
3. **Agent Traces** — Decision timeline, reasoning for each action
4. **Cost Tracker** — Token spend, Athena bytes scanned
5. **Remediation History** — Actions taken, before/after scores

## Step 7: Restore Clean Data

```bash
uv run python data/upload_to_s3.py --source data/raw --bucket dq-agent-demo-<ACCOUNT_ID> --prefix raw/yellow_taxi --overwrite
```

## Step 8: Invoke via AgentCore (Cloud)

```bash
agentcore invoke '{"prompt": "Scan raw_yellow_taxi partition year=2024/month=01 for all quality issues. Diagnose and remediate."}'
```

## Cleanup

```bash
cd cdk
uv run --extra cdk -- npx cdk destroy --app "python3 app.py" --all
agentcore destroy --agent dq_agent
```
