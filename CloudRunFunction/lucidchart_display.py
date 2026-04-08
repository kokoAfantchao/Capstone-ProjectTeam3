"""
lucidchart_display.py
Uses the LucidChart Data Linking API to push BigQuery table data
into a LucidChart document so shapes reflect live dataset values.

Environment variables required:
  LUCIDCHART_API_TOKEN   - Your LucidChart OAuth2 / personal API token
  LUCIDCHART_DOCUMENT_ID - The document ID from the LucidChart URL
                           e.g. https://lucid.app/lucidchart/<DOCUMENT_ID>/edit

Usage:
  from lucidchart_display import push_summary_to_lucidchart, push_table_rows_to_lucidchart
"""

import os
import json
import requests
from bq_manager import get_dataset_summary


# ──────────────────────────────────────────────
# LucidChart API helpers
# ──────────────────────────────────────────────

LUCID_API_BASE = "https://api.lucid.co"

# Read once at module level — set these in your environment or Dockerfile
LUCIDCHART_API_TOKEN   = os.environ.get("LUCIDCHART_API_TOKEN", "")
LUCIDCHART_DOCUMENT_ID = os.environ.get("LUCIDCHART_DOCUMENT_ID", "")


def _get_headers() -> dict:
    """Build the required HTTP headers for LucidChart API requests."""
    if not LUCIDCHART_API_TOKEN:
        raise EnvironmentError(
            "LUCIDCHART_API_TOKEN env var is not set. "
            "Create a token at https://lucid.app/oauth/app"
        )
    return {
        "Authorization": f"Bearer {LUCIDCHART_API_TOKEN}",
        "Content-Type": "application/json",
        "Lucid-Api-Version": "1",
    }


def _get_document_id() -> str:
    """Return the target LucidChart document ID from module-level constant."""
    if not LUCIDCHART_DOCUMENT_ID:
        raise EnvironmentError(
            "LUCIDCHART_DOCUMENT_ID env var is not set. "
            "Copy the ID from your LucidChart document URL."
        )
    return LUCIDCHART_DOCUMENT_ID


# ──────────────────────────────────────────────
# Data formatting helpers
# ──────────────────────────────────────────────

def _format_summary_as_lucid_collection(summary: dict) -> dict:
    """
    Convert a dataset summary dict into the LucidChart Data Collection format.
    Each BQ table becomes one row in the collection.

    LucidChart Data Collection payload shape:
    {
      "dataSourceName": "BigQuery Dataset",
      "data": [
        { "id": "users",  "label": "users",  "row_count": 1200 },
        ...
      ]
    }
    """
    rows = []
    for table in summary["tables"]:
        rows.append({
            "id": table["table_id"],          # unique key LucidChart uses to link shapes
            "label": table["table_id"],
            "row_count": table["row_count"],
            "dataset": summary["dataset_id"],
        })

    return {
        "dataSourceName": f"BigQuery – {summary['dataset_id']}",
        "data": rows,
    }


def _format_table_rows_as_lucid_collection(
    table_id: str,
    rows: list[dict],
    schema: list[dict],
) -> dict:
    """
    Convert raw BQ table rows + schema into a LucidChart Data Collection.
    Adds a synthetic 'id' field (row index) if none is detected.
    """
    id_field = next((f["name"] for f in schema if "id" in f["name"].lower()), None)

    lucid_rows = []
    for i, row in enumerate(rows):
        record = {k: str(v) for k, v in row.items()}   # LucidChart expects strings
        record["id"] = str(row.get(id_field, i))        # stable row identifier
        lucid_rows.append(record)

    return {
        "dataSourceName": f"BigQuery – {table_id}",
        "data": lucid_rows,
    }


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────



def list_lucidchart_collections() -> list[dict]:
    """
    Return all existing data collections attached to the LucidChart document.
    Useful for inspecting previously pushed data.
    """
    doc_id = _get_document_id()
    url = f"{LUCID_API_BASE}/documents/{doc_id}/data-collections"

    response = requests.get(url, headers=_get_headers(), timeout=15)
    response.raise_for_status()
    return response.json()


def delete_lucidchart_collection(collection_id: str) -> bool:
    """
    Delete a data collection from the LucidChart document by its ID.
    Returns True on success.
    """
    doc_id = _get_document_id()
    url = f"{LUCID_API_BASE}/documents/{doc_id}/data-collections/{collection_id}"

    response = requests.delete(url, headers=_get_headers(), timeout=15)
    response.raise_for_status()
    print(f"[LucidChart] Deleted collection {collection_id}")
    return True
