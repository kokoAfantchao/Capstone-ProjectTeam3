"""
bq_manager.py
Handles all BigQuery operations:
- List all tables and row counts in a dataset
- Query a specific table with optional row limit
- Get schema of a table
- Get the most recent rows from a table
"""

import os
from datetime import datetime
from typing import Optional
from google.cloud import bigquery
from google.oauth2 import service_account

# Read once at module level — set these in your environment or Dockerfile
BQ_PROJECT = os.environ.get("BQ_PROJECT", "ksu-team-2")
BQ_DATASET = os.environ.get("BQ_DATASET", "capstone_dev")
RUn_ENV = os.environ.get("RUN_ENV", "local_dev")  # "local" or "cloudrun"



def get_client() -> bigquery.Client:
    if RUn_ENV != "local_dev":
      return bigquery.Client(project=BQ_PROJECT)
    else:
        credentials = service_account.Credentials.from_service_account_file(
            os.path.expanduser("../ActiveDirectoryScript/service-account.json")
        )
        return bigquery.Client(project=BQ_PROJECT, credentials=credentials)


def query_table(table_id: str, dataset_id: str = None, limit: int = 100) -> list[dict]:
    """
    Query and return rows from a table as a list of dicts.
    Args:
        table_id:   Name of the BigQuery table.
        dataset_id: Override dataset (falls back to BQ_DATASET env var).
        limit:      Max number of rows to return (default 100).
    """
    client = get_client()
    dataset_id = dataset_id or BQ_DATASET

    query = f"""
        SELECT *
        FROM `{BQ_PROJECT}.{dataset_id}.{table_id}`
        LIMIT {limit}
    """

    results = client.query(query).result()
    return [dict(row) for row in results]

# get latest Datetime  from  the table snapshot_times
## the table snapshot_times has Oone columns:dateTime :2026-03-30 03:50:34.455944 UTC
def get_latestSnapshot() -> Optional[datetime]:
    client = get_client()
    query = f"""
        SELECT MAX(snapshot_time) as latest_snapshot
        FROM `{BQ_PROJECT}.{BQ_DATASET}.snapshot_times`
    """
    results = client.query(query).result()
    row = next(results, None)
    return row["latest_snapshot"] if row else None



def get_dataset_summary(dataset_id: str = None):
    """
    Return a high-level summary of the dataset:
    total tables, total rows, and per-table breakdown.
    """
    get_client()  # Ensure we can connect before proceeding
    dataset_id = dataset_id or BQ_DATASET
     
    get_client().list_tables(dataset_id)  # This will raise an error if the dataset doesn't exist or we lack permissions

    for table in get_client().list_tables(dataset_id):
        print(f"Table: {table.table_id}, Rows: {table.num_rows}, Size: {table.num_bytes} bytes")
