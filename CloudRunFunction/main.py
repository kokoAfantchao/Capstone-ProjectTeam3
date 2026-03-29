import os
import json
from flask import Flask, request, jsonify
from google.cloud import bigquery

app = Flask(__name__)

# Use the Google Cloud SDK standard environment variable for authentication
# Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
# Set BQ_PROJECT=your-project-id
# Set BQ_DATASET=your-dataset-id

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
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Dataset: {dataset_id}</h1>
            <p>Select a table to view details</p>
            <div class="table-container">
                {tables_html if tables_html else '<p>No tables found.</p>'}
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/big-querry/eventlistener", methods=["POST"])
def bq_event_listener():
    if request.method == "POST":
        # Parse the JSON payload from the request
        data = request.get_json(silent=True) or {}
        
        # Log the received data to the console (for Cloud Run logs)
        print(f"--- Event Listener Triggered ---")
        print(json.dumps(data, indent=2))
        print(f"--------------------------------")
        
        # Return a JSON response acknowledging receipt
        return jsonify({
            "status": "success",
            "message": "Notification received successfully",
            "received_data": data
        }), 200

    # For GET requests, return a simple HTML page or message
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Event Listener</title>
        <style>
            body { font-family: sans-serif; padding: 40px; }
            .notification { background: #e8f0fe; border-left: 4px solid #1a73e8; padding: 20px; }
        </style>
    </head>
    <body>
        <div class="notification">
            <h2>BigQuery Event Listener is Active</h2>
            <p>Ready to receive POST requests with JSON payloads.</p>
        </div>
    </body>
    </html>
    """, 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
