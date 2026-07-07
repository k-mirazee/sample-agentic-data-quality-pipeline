#!/usr/bin/env python3
"""Upload local Parquet files to S3 data lake with Hive-style partitioning.

Usage:
    python data/upload_to_s3.py --source data/raw --bucket dq-agent-demo-<ACCOUNT> --prefix raw/yellow_taxi
    python data/upload_to_s3.py --source data/chaos --bucket dq-agent-demo-<ACCOUNT> --overwrite
    python data/upload_to_s3.py --file data/chaos/yellow_tripdata_2025-09.parquet \
        --bucket dq-agent-demo-<ACCOUNT> --overwrite
"""

import argparse
import re
from pathlib import Path

import boto3

GLUE_DATABASE = "dq_agent_demo"
GLUE_TABLE = "raw_yellow_taxi"


def _partition_values(filename: str) -> tuple[str, str] | None:
    """Extract (year, month) from a filename like yellow_tripdata_2024-01.parquet."""
    match = re.search(r"(\d{4})-(\d{2})", filename)
    return (match.group(1), match.group(2)) if match else None


def register_partitions(bucket: str, prefix: str, partitions: list[tuple[str, str]]) -> None:
    """Register uploaded partitions in the Glue catalog (idempotent).

    The CDK-defined table starts with zero partitions; Glue DQ and Athena only
    see data in partitions the catalog knows about.
    """
    glue = boto3.client("glue")
    try:
        table = glue.get_table(DatabaseName=GLUE_DATABASE, Name=GLUE_TABLE)["Table"]
    except Exception as e:
        print(f"Warning: could not read table {GLUE_DATABASE}.{GLUE_TABLE} — skipping partition registration: {e}")
        return

    for year, month in partitions:
        try:
            glue.get_partition(DatabaseName=GLUE_DATABASE, TableName=GLUE_TABLE, PartitionValues=[year, month])
            continue  # already registered
        except glue.exceptions.EntityNotFoundException:
            pass
        storage = dict(table["StorageDescriptor"])
        storage["Location"] = f"s3://{bucket}/{prefix}/year={year}/month={month}/"
        glue.create_partition(
            DatabaseName=GLUE_DATABASE,
            TableName=GLUE_TABLE,
            PartitionInput={"Values": [year, month], "StorageDescriptor": storage},
        )
        print(f"Registered partition year={year}/month={month}")


def upload_files(files: list[Path], bucket: str, prefix: str, overwrite: bool = False) -> list[str]:
    """Upload parquet files to S3 with year=/month= partitioning derived from filenames."""
    s3 = boto3.client("s3")
    uploaded = []
    partitions = []

    for f in files:
        values = _partition_values(f.name)
        if not values:
            print(f"Skipping {f.name} (can't parse year-month)")
            continue

        year, month = values
        s3_key = f"{prefix}/year={year}/month={month}/trips.parquet"

        if not overwrite:
            try:
                s3.head_object(Bucket=bucket, Key=s3_key)
                print(f"Skipping s3://{bucket}/{s3_key} (exists, use --overwrite)")
                continue
            except s3.exceptions.ClientError:
                pass

        print(f"Uploading {f.name} → s3://{bucket}/{s3_key}")
        s3.upload_file(str(f), bucket, s3_key)
        uploaded.append(s3_key)
        partitions.append(values)

    if partitions:
        register_partitions(bucket, prefix, partitions)

    print(f"\nUploaded {len(uploaded)} file(s)")
    return uploaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload Parquet data to S3 data lake")
    parser.add_argument("--source", help="Local directory with .parquet files")
    parser.add_argument("--file", help="Single .parquet file to upload")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--prefix", default="raw/yellow_taxi", help="S3 key prefix")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    if bool(args.source) == bool(args.file):
        parser.error("Provide exactly one of --source or --file")

    files = [Path(args.file)] if args.file else sorted(Path(args.source).glob("*.parquet"))
    upload_files(files, args.bucket, args.prefix, args.overwrite)
