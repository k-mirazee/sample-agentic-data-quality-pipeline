#!/usr/bin/env python3
"""Upload local Parquet files to S3 data lake with Hive-style partitioning.

Usage:
    python data/upload_to_s3.py --source data/raw --bucket dq-agent-demo-015331669295 --prefix raw/yellow_taxi
    python data/upload_to_s3.py --source data/chaos --bucket dq-agent-demo-015331669295 --prefix raw/yellow_taxi --overwrite
"""

import argparse
import re
from pathlib import Path

import boto3


def upload_to_s3(source_dir: str, bucket: str, prefix: str, overwrite: bool = False) -> list[str]:
    """Upload parquet files to S3 with year=/month= partitioning derived from filenames."""
    s3 = boto3.client("s3")
    uploaded = []

    for f in sorted(Path(source_dir).glob("*.parquet")):
        # Extract year and month from filename like yellow_tripdata_2024-01.parquet
        match = re.search(r"(\d{4})-(\d{2})", f.name)
        if not match:
            print(f"Skipping {f.name} (can't parse year-month)")
            continue

        year, month = match.group(1), match.group(2)
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

    print(f"\nUploaded {len(uploaded)} file(s)")
    return uploaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload Parquet data to S3 data lake")
    parser.add_argument("--source", required=True, help="Local directory with .parquet files")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--prefix", default="raw/yellow_taxi", help="S3 key prefix")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    upload_to_s3(args.source, args.bucket, args.prefix, args.overwrite)
