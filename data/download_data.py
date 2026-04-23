#!/usr/bin/env python3
"""Download NYC TLC Yellow Taxi trip data from the public source."""

import argparse
import os

import requests

TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def download_months(
    start_year: int,
    start_month: int,
    num_months: int,
    output_dir: str,
) -> list[str]:
    """Download yellow taxi parquet files for the specified month range."""
    downloaded = []
    os.makedirs(output_dir, exist_ok=True)

    for i in range(num_months):
        month = start_month + i
        year = start_year + (month - 1) // 12
        month = ((month - 1) % 12) + 1

        filename = f"yellow_tripdata_{year}-{month:02d}.parquet"
        url = f"{TLC_BASE_URL}/{filename}"
        local_path = os.path.join(output_dir, filename)

        if os.path.exists(local_path):
            print(f"Skipping {filename} (already exists)")
            downloaded.append(local_path)
            continue

        print(f"Downloading {url}...")
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = os.path.getsize(local_path) / 1e6
        print(f"  Saved to {local_path} ({size_mb:.1f} MB)")
        downloaded.append(local_path)

    return downloaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download NYC TLC taxi data")
    parser.add_argument("--start-year", type=int, default=2024)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--num-months", type=int, default=3)
    parser.add_argument("--output-dir", default="data/raw")
    args = parser.parse_args()

    files = download_months(args.start_year, args.start_month, args.num_months, args.output_dir)
    print(f"\nDownloaded {len(files)} file(s)")
