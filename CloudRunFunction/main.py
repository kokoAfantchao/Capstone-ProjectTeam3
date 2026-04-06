import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from google.cloud import bigquery
from bq_manager import get_dataset_summary, query_table, get_table_schema, get_latestSnapshot
from lucidchart_display import LUCIDCHART_API_TOKEN, LUCIDCHART_DOCUMENT_ID, push_summary_to_lucidchart, push_table_rows_to_lucidchart, list_lucidchart_collections

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# Global variable to keep track of the latest event
latest_event_info = {
    "event": None,
    "latest_snapshot": None
}


# ──────────────────────────────────────────────
# Startup checks
# ──────────────────────────────────────────────

def test_bigquery_auth() -> bool:
    """
    Verify that BigQuery credentials are valid and the configured
    project/dataset is reachable. Logs success or a detailed error.
    Returns True on success, False on failure.
    """
    try:
        client = bigquery.Client(project=BQ_PROJECT)
        # A lightweight probe: list datasets (does not read table data)
        list(client.list_datasets(max_results=1))
        log.info("[BigQuery] Authentication OK — project: %s, dataset: %s", BQ_PROJECT, BQ_DATASET)
        return True
    except Exception as e:
        log.error("[BigQuery] Authentication FAILED — %s", str(e))
        log.error("[BigQuery] Ensure GOOGLE_APPLICATION_CREDENTIALS and BQ_PROJECT are set correctly.")
        return False


def test_lucidchart_api() -> bool:
    """
    Verify that the LucidChart API token and document ID are configured
    and the API is reachable. Logs success or a detailed error.
    Returns True on success, False on failure.
    """
    import requests as req

    if not LUCIDCHART_API_TOKEN:
        log.error("[LucidChart] LUCIDCHART_API_TOKEN is not set.")
        return False
    if not LUCIDCHART_DOCUMENT_ID:
        log.error("[LucidChart] LUCIDCHART_DOCUMENT_ID is not set.")
        return False

    try:
        url = f"https://api.lucid.co/documents/{LUCIDCHART_DOCUMENT_ID}/data-collections"
        headers = {
            "Authorization": f"Bearer {LUCIDCHART_API_TOKEN}",
            "Content-Type": "application/json",
            "Lucid-Api-Version": "1",
        }
        response = req.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        log.info("[LucidChart] API connection OK — document: %s", LUCIDCHART_DOCUMENT_ID)
        return True
    except Exception as e:
        log.error("[LucidChart] API connection FAILED — %s", str(e))
        log.error("[LucidChart] Ensure LUCIDCHART_API_TOKEN and LUCIDCHART_DOCUMENT_ID are set correctly.")
        return False


# Run both checks at startup
test_bigquery_auth()
test_lucidchart_api()

@app.route("/")
def hello_world():
    project_id = os.environ.get("BQ_PROJECT", "my-gcp-project")
    dataset_id = os.environ.get("BQ_DATASET", "my_dataset")
    
    # Initialize the BigQuery client
    # The client will automatically look for the GOOGLE_APPLICATION_CREDENTIALS environment variable
    client = bigquery.Client(project=project_id)
    
    # Query the dataset's __TABLES__ meta-table to get row counts efficiently
    query = f"""
        SELECT table_id, row_count
        FROM `{project_id}.{dataset_id}.__TABLES__`
    """
    
    try:
        query_job = client.query(query)
        results = query_job.result()
        
        tables_html = ""
        for row in results:
            tables_html += f"""
                <button class="table-button">
                    {row.table_id} <span class="badge">{row.row_count}</span>
                </button>
            """
    except Exception as e:
        tables_html = f"<p style='color: red;'>Error querying BigQuery: {str(e)}</p>"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BigQuery Tables</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background-color: #f8f9fa;
                padding-top: 40px;
            }}
            .card {{
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                max-width: 600px;
                width: 100%;
            }}
            h1 {{ color: #1a73e8; margin-bottom: 20px; }}
            .table-container {{
                display: flex;
                flex-direction: column;
                gap: 15px;
                margin-top: 30px;
            }}
            .table-button {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 25px;
                font-size: 1.1em;
                color: #3c4043;
                background-color: #fff;
                border: 1px solid #dadce0;
                border-radius: 8px;
                cursor: pointer;
                transition: background-color 0.2s, box-shadow 0.2s;
            }}
            .table-button:hover {{
                background-color: #f1f3f4;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }}
            .badge {{
                background-color: #e8f0fe;
                color: #1a73e8;
                padding: 4px 12px;
                border-radius: 20px;
                font-weight: 600;
                font-size: 0.9em;
            }}
            .top-bar {{
                background-color: #34a853;
                color: white;
                padding: 10px 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                font-weight: bold;
                display: none;
                width: 100%;
                max-width: 600px;
                text-align: center;
                box-sizing: border-box;
            }}
        </style>
    </head>
    <body>
        <div id="event-banner" class="top-bar">
            Latest Event: <span id="event-time">None</span>
        </div>

        <div class="card">
            <h1>Dataset: {dataset_id}</h1>
            <p>Select a table to view details</p>
            <div class="table-container">
                {tables_html if tables_html else '<p>No tables found.</p>'}
            </div>
        </div>

        <script>
            let lastKnownTime = null;

            function pollForEvents() {{
                fetch('/api/latest-event')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.time && data.time !== lastKnownTime) {{
                            lastKnownTime = data.time;
                            
                            // Update top banner
                            document.getElementById('event-banner').style.display = 'block';
                            document.getElementById('event-time').innerText = data.time;
                            
                            // Show pop-up notification
                            alert("New Event Received at " + data.time + "\\n\\nData: " + JSON.stringify(data.data));
                        }}
                    }})
                    .catch(error => console.error('Error fetching event data:', error));
            }}

            // Poll every 3 seconds
            setInterval(pollForEvents, 3000);
            pollForEvents(); // Initial check
        </script>
    </body>
    </html>
    """

# New endpoint for the frontend to poll the latest event status
@app.route("/api/latest-event", methods=["GET"])
def get_latest_event():
    return jsonify(latest_event_info)

@app.route("/big-querry/eventlistener", methods=["GET", "POST"])
def bq_event_listener():
    global latest_event_info # Use global variable to store the latest event info
    event_time = datetime.utcnow().isoformat() + "Z"  # ISO format with UTC timezone
    # 2026-03-30 03:50:34.455944 UTC id the time returned from get_latestSnapshot() function
    latest_snapshot = get_latestSnapshot()
    event_data = {
        "event": "BigQuery Table Update",
        "latest_snapshot": latest_snapshot.isoformat() + "Z" if latest_snapshot else None
    }
    latest_event_info = event_data


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


