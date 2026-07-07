#!/usr/bin/env python3
"""Chaos Injector — Introduces controlled data quality issues into Parquet datasets.

Usage:
    python data/chaos_injector.py --input data/raw/yellow_tripdata_2024-01.parquet \
        --output data/chaos/yellow_tripdata_2024-01.parquet
    python data/chaos_injector.py --input data/raw/ --output data/chaos/
"""

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)["chaos_config"]


def inject_nulls(df: pd.DataFrame, config: dict, rng: np.random.Generator) -> pd.DataFrame:
    if not config.get("enabled"):
        return df
    for col_cfg in config.get("columns", []):
        col, rate = col_cfg["column"], col_cfg["null_rate"]
        if col in df.columns:
            mask = rng.random(len(df)) < rate
            df.loc[mask, col] = None
            print(f"  [null] {col}: {mask.sum():,} rows ({rate * 100:.1f}%)")
    return df


def inject_outliers(df: pd.DataFrame, config: dict, rng: np.random.Generator) -> pd.DataFrame:
    if not config.get("enabled"):
        return df
    for rule in config.get("rules", []):
        col, rate = rule["column"], rule["inject_rate"]
        if col not in df.columns:
            continue
        mask = rng.random(len(df)) < rate
        n = mask.sum()
        if "values" in rule:
            values = rng.choice(rule["values"], size=n)
        else:
            values = rng.uniform(rule["min"], rule["max"], size=n)
        df.loc[mask, col] = values
        print(f"  [outlier] {col}: {n:,} rows ({rate * 100:.1f}%)")
    return df


def inject_schema_drift(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    if not config.get("enabled"):
        return df
    for action in config.get("actions", []):
        t = action["type"]
        if t == "rename_column" and action["from_name"] in df.columns:
            df = df.rename(columns={action["from_name"]: action["to_name"]})
            print(f"  [schema] Renamed {action['from_name']} → {action['to_name']}")
        elif t == "add_column":
            df[action["name"]] = action.get("fill_value", 0.0)
            print(f"  [schema] Added column {action['name']}")
        elif t == "drop_column" and action["name"] in df.columns:
            df = df.drop(columns=[action["name"]])
            print(f"  [schema] Dropped column {action['name']}")
        elif t == "change_type" and action["column"] in df.columns:
            df[action["column"]] = df[action["column"]].astype(action["new_dtype"])
            print(f"  [schema] Changed {action['column']} type → {action['new_dtype']}")
    return df


def inject_duplicates(df: pd.DataFrame, config: dict, rng: np.random.Generator) -> pd.DataFrame:
    if not config.get("enabled"):
        return df
    n_exact = int(len(df) * config.get("exact_duplicates", 0))
    n_near = int(len(df) * config.get("near_duplicates", 0))

    if n_exact > 0:
        idx = rng.choice(len(df), size=n_exact, replace=True)
        df = pd.concat([df, df.iloc[idx].copy()], ignore_index=True)
        print(f"  [duplicate] {n_exact:,} exact duplicates")

    if n_near > 0:
        idx = rng.choice(len(df), size=n_near, replace=True)
        near = df.iloc[idx].copy()
        for col in near.select_dtypes(include=["float64"]).columns[:3]:
            near[col] = near[col] + rng.normal(0, 0.01, size=n_near)
        df = pd.concat([df, near], ignore_index=True)
        print(f"  [duplicate] {n_near:,} near-duplicates")
    return df


def inject_freshness_issues(df: pd.DataFrame, config: dict, rng: np.random.Generator) -> pd.DataFrame:
    if not config.get("enabled"):
        return df
    days, rate = config.get("backdate_days", 7), config.get("affected_rate", 0.1)
    for col in ["tpep_pickup_datetime", "tpep_dropoff_datetime"]:
        if col in df.columns:
            mask = rng.random(len(df)) < rate
            df.loc[mask, col] = df.loc[mask, col] - pd.Timedelta(days=days)
            print(f"  [freshness] {col}: {mask.sum():,} rows backdated {days}d")
    return df


def inject_format_violations(df: pd.DataFrame, config: dict, rng: np.random.Generator) -> pd.DataFrame:
    if not config.get("enabled"):
        return df
    for rule in config.get("rules", []):
        col, rate = rule["column"], rule["inject_rate"]
        if col not in df.columns:
            continue
        mask = rng.random(len(df)) < rate
        df.loc[mask, col] = rng.choice(rule["inject_values"], size=mask.sum())
        print(f"  [format] {col}: {mask.sum():,} rows ({rate * 100:.1f}%)")
    return df


def restore_integer_dtypes(df: pd.DataFrame, original_schema: pa.Schema) -> pd.DataFrame:
    """Cast integer columns back to nullable integer dtypes after injection.

    Pandas silently upcasts int columns to float64 when nulls are injected;
    writing that back produces parquet files whose physical types (DOUBLE)
    conflict with the Glue catalog (bigint/int), and Athena and Glue DQ then
    refuse to read the partition (HIVE_BAD_DATA). Nullable Int32/Int64 keep
    the physical schema stable while still carrying the injected nulls.
    """
    for field in original_schema:
        if field.name not in df.columns or not pa.types.is_integer(field.type):
            continue
        target = "Int32" if field.type.bit_width <= 32 else "Int64"
        if str(df[field.name].dtype) != target:
            df[field.name] = pd.to_numeric(df[field.name], errors="coerce").round().astype(target)
    return df


def run_chaos(input_path: str, output_path: str, config: dict) -> dict:
    """Apply all configured chaos injections to a Parquet file."""
    print(f"\nProcessing: {input_path}")
    original_schema = pq.read_schema(input_path)
    df = pd.read_parquet(input_path)
    original_rows = len(df)
    print(f"  Original: {original_rows:,} rows, {len(df.columns)} columns")

    rng = np.random.default_rng(config.get("seed", 42))

    df = inject_nulls(df, config.get("null_injection", {}), rng)
    df = inject_outliers(df, config.get("outlier_injection", {}), rng)
    df = inject_duplicates(df, config.get("duplicate_injection", {}), rng)
    df = inject_freshness_issues(df, config.get("freshness_issues", {}), rng)
    df = inject_format_violations(df, config.get("format_violations", {}), rng)
    df = inject_schema_drift(df, config.get("schema_drift", {}))  # Last — may change columns

    df = restore_integer_dtypes(df, original_schema)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"  Output: {len(df):,} rows, {len(df.columns)} columns → {output_path}")

    return {"input": input_path, "output": output_path, "original_rows": original_rows, "output_rows": len(df)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chaos Injector for data quality demos")
    parser.add_argument("--input", required=True, help="Input Parquet file or directory")
    parser.add_argument("--output", required=True, help="Output Parquet file or directory")
    parser.add_argument("--config", default="data/chaos_config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    if os.path.isdir(args.input):
        for f in sorted(Path(args.input).glob("*.parquet")):
            run_chaos(str(f), os.path.join(args.output, f.name), config)
    else:
        run_chaos(args.input, args.output, config)
