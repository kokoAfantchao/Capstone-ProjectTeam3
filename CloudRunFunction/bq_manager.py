"""
bq_manager.py
Handles all BigQuery operations:
- List all tables and row counts in a dataset
- Query a specific table with optional row limit
- Get schema of a table
- Get the most recent rows from a table
"""

import os
from google.cloud import bigquery

# Read once at module level — set these in your environment or Dockerfile
BQ_PROJECT = os.environ.get("BQ_PROJECT", "ksu-team-2")
BQ_DATASET = os.environ.get("BQ_DATASET", "apstone_dev")


def get_client() -> bigquery.Client:
    """Initialize and return a BigQuery client using env vars."""
    # Credentials are picked up automatically from GOOGLE_APPLICATION_CREDENTIALS
    return bigquery.Client(project=BQ_PROJECT)


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
def get_latestSnapshot() -> datetime:
    client = get_client()
    query = f"""
        SELECT MAX(snapshot_time) as latest_snapshot
        FROM `{BQ_PROJECT}.{BQ_DATASET}.snapshot_times`
    """
    results = client.query(query).result()
    row = next(results, None)
    return row["latest_snapshot"] if row else None



def get_dataset_summary(dataset_id: str = None) -> dict:
    """
    Return a high-level summary of the dataset:
    total tables, total rows, and per-table breakdown.
    """
    tables = list_tables_with_row_counts(dataset_id)
    total_rows = sum(t["row_count"] for t in tables)

    return {
        "dataset_id": dataset_id or BQ_DATASET,
        "total_tables": len(tables),
        "total_rows": total_rows,
        "tables": tables
    }
