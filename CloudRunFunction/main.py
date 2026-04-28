import os
import json
import logging
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, redirect
import requests as http_requests
from google.cloud import bigquery
from bq_manager import get_dataset_summary, get_latestSnapshot, BQ_PROJECT, BQ_DATASET
from lucidchart_display import LUCIDCHART_API_TOKEN, LUCIDCHART_DOCUMENT_ID
from lucidchart_builder import trigger_lucid_import, LUCID_CLIENT_SECRET
from google.cloud import secretmanager as secretmanager
# This is my first comment

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)


# Global variable to keep track of the latest event
latest_event_info = {
    "event": None,
    "latest_snapshot": None
}

# ──────────────────────────────────────────────
# Secret Manager Helpers
# ──────────────────────────────────────────────
# Secret Manager Helpers
# ──────────────────────────────────────────────    
def get_secret(secret_id):
    if secretmanager is None:
        log.warning("[SecretManager] Client library not available; skipping read for %s", secret_id)
        return None
    try:
        from bq_manager import BQ_PROJECT
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{BQ_PROJECT}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        log.warning("[SecretManager] Could not retrieve %s: %s", secret_id, e)
        return None

def save_secret(secret_id, payload_str):
    if secretmanager is None:
        log.warning("[SecretManager] Client library not available; skipping save for %s", secret_id)
        return
    try:
        from bq_manager import BQ_PROJECT
        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{BQ_PROJECT}/secrets/{secret_id}"
        payload = payload_str.encode("UTF-8")
        client.add_secret_version(request={"parent": parent, "payload": {"data": payload}})
        log.info("[SecretManager] Saved new version for %s", secret_id)
    except Exception as e:
        log.error("[SecretManager] Failed to save %s (ensure the secret exists): %s", secret_id, e)

def load_tokens_from_secret_manager():
    log.info("[SecretManager] Attempting to load LucidChart tokens...")
    rt = get_secret("lucid_refresh_token")
    if rt:
        os.environ["LUCID_REFRESH_TOKEN"] = rt
    at = get_secret("lucid_access_token")
    if at:
        os.environ["LUCID_ACCESS_TOKEN"] = at


# History of every LucidChart import triggered by the event listener
lucid_imports_history = []  # list of {"timestamp": str, "result": dict}


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
    import requests as req

    # _get_valid_access_token is defined later in the file; fall back to a
    # simple env lookup when called at module-load time (startup probe only).
    try:
        dynamic_token = _get_valid_access_token()
    except NameError:
        dynamic_token = os.environ.get("LUCID_ACCESS_TOKEN", LUCIDCHART_API_TOKEN)

    if not dynamic_token:
        log.error("[LucidChart] API token is not set.")
        return False
    if not LUCIDCHART_DOCUMENT_ID:
        log.error("[LucidChart] LUCIDCHART_DOCUMENT_ID is not set.")
        return False

    try:
        url = f"https://api.lucid.co/documents/{LUCIDCHART_DOCUMENT_ID}/data-collections"
        headers = {
            "Authorization": f"Bearer {dynamic_token}",
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
load_tokens_from_secret_manager()
test_lucidchart_api()

@app.route("/")
def hello_world():
    # Use BQ_PROJECT/BQ_DATASET and the authenticated client from bq_manager
    project_id = BQ_PROJECT
    dataset_id = BQ_DATASET

    # Use get_client() which loads credentials from the service account JSON
    from bq_manager import get_client
    client = get_client()

    query = f"""
        SELECT table_id, row_count
        FROM `{project_id}.{dataset_id}.__TABLES__`
    """

    try:
        query_job = client.query(query)
        results = query_job.result()
        
                
        tables_html = ""
        for table in results:
            log.info(f"Table: {table.table_id}, Rows: {table.row_count}")

            tables_html += f"""
                <button class="table-button">
                    {table.table_id} <span class="badge">{table.row_count}</span>
                    </br>
                    <p style="font-size: 0.8em; color: #666;">Click for details</p>
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

# In-memory set to keep track of processed CloudEvent IDs
processed_events = set()

@app.route("/big-querry/eventlistener", methods=["POST"])
def bq_event_listener():
    global latest_event_info

    # 1. At-Least-Once Delivery check
    event_id = request.headers.get("ce-id")
    if event_id:
        if event_id in processed_events:
            log.info(f"Skipping duplicate event ID: {event_id}")
            return jsonify({"status": "Ignored: Duplicate event"}), 200
        
        # Add to processed events (in a production environment, use Redis or a DB)
        processed_events.add(event_id)
        # Prevent map from growing infinitely in memory
        if len(processed_events) > 1000:
            # Remove an arbitrary item to keep size capped
            processed_events.pop()

    # 2. Check for Job Completion (BigQuery specific)
    try:
        payload = request.get_json(silent=True) or {}
        proto_payload = payload.get("protoPayload", {})
        service_data = proto_payload.get("serviceData", {})
        
        # Check if this is a job completed event
        is_completed = service_data.get("jobCompletedEvent") is not None
        
        # If protoPayload is present but it's NOT a completed event, ignore it.
        # (If protoPayload is missing, this might be a generic invoke, so we let it proceed)
        if proto_payload and not is_completed:
            log.info(f"Skipping job start event: {event_id}")
            return jsonify({"status": "Ignored: Job not finished."}), 200
    except Exception as e:
        log.warning(f"Failed to parse payload for job completion check: {e}")


    # ── POST: update snapshot tracker then push to LucidChart ──
    try:
        lucid_result = trigger_lucid_import()
        log.info("[LucidChart] Import complete — %s", lucid_result)

        lucid_imports_history.append({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "result": lucid_result,
        })

        return jsonify({
            "status": "success",
            "lucidchart": lucid_result,
        }), 200
    except Exception as e:
        log.error("[LucidChart] Import failed — %s", str(e))
        return jsonify({
            "status": "partial",
            "lucidchart_error": str(e),
        }), 500


# ──────────────────────────────────────────────
# LucidChart import history  (/lucidcharts-history)
# ──────────────────────────────────────────────

@app.route("/lucidcharts-history")
def lucidcharts_history():
    rows_html = ""
    for i, entry in enumerate(reversed(lucid_imports_history), 1):
        ts  = entry["timestamp"]
        res = entry["result"]
        doc_id   = (res.get("lucidchart_result") or {}).get("documentId", "—")
        nodes    = res.get("nodes_count", "—")
        edges    = res.get("edges_count", "—")
        pages    = res.get("pages_count", "—")
        doc_link = (f'<a href="https://lucid.app/lucidchart/{doc_id}/edit" '
                    f'target="_blank">{doc_id}</a>') if doc_id != "—" else "—"
        rows_html += f"""
        <tr>
          <td>{len(lucid_imports_history) - i + 1}</td>
          <td>{ts}</td>
          <td>{nodes}</td>
          <td>{edges}</td>
          <td>{pages}</td>
          <td style="word-break:break-all">{doc_link}</td>
        </tr>"""

    if not rows_html:
        rows_html = '<tr><td colspan="6" style="text-align:center;color:#888">No imports yet.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>LucidChart Import History</title>
<style>
  body{{font-family:sans-serif;max-width:960px;margin:40px auto;padding:0 16px;background:#f8f9fa}}
  h1{{color:#1a73e8}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;
         box-shadow:0 2px 8px rgba(0,0,0,.1);overflow:hidden}}
  th{{background:#1a73e8;color:#fff;padding:12px 16px;text-align:left}}
  td{{padding:11px 16px;border-bottom:1px solid #e0e0e0;vertical-align:top}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#f1f3f4}}
  a{{color:#1a73e8}}
  .back{{display:inline-block;margin-bottom:20px;color:#1a73e8;text-decoration:none}}
  .badge{{background:#e8f0fe;color:#1a73e8;padding:2px 10px;border-radius:12px;font-size:.85em}}
</style></head><body>
<a class="back" href="/">← Back to dashboard</a>
<h1>LucidChart Import History
  <span class="badge">{len(lucid_imports_history)} total</span>
</h1>
<table>
  <thead><tr>
    <th>#</th><th>Timestamp (UTC)</th><th>Nodes</th><th>Edges</th><th>Pages</th><th>Document ID</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</body></html>"""


# ──────────────────────────────────────────────
# LucidChart OAuth2  (/auth/lucidchart  +  callback)
# ──────────────────────────────────────────────

_LUCID_AUTH_URL   = "https://lucid.app/oauth2/authorize"
_LUCID_TOKEN_URL  = "https://api.lucid.co/oauth2/token"
_LUCID_CLIENT_ID  = os.environ.get("LUCID_CLIENT_ID",
                         "NEhXzDpgVSIhQKJSXzFyG0rJYshiuh5rfHfevyz1")
_LUCID_REDIRECT   = ("https://lucid.app/oauth2/clients/"
                     "NEhXzDpgVSIhQKJSXzFyG0rJYshiuh5rfHfevyz1/redirect")
SCOPES = "lucidchart.document.content offline_access"


def _save_tokens(tokens: dict):
    """Persist access + refresh tokens to env and Secret Manager, tracking expiry."""
    from datetime import timedelta
    access_token  = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in    = tokens.get("expires_in", 3600)
    if access_token:
        os.environ["LUCID_ACCESS_TOKEN"] = access_token
        # Store absolute expiry so we can auto-refresh (subtract 5 min buffer)
        expiry = (datetime.utcnow() + timedelta(seconds=int(expires_in) - 300)).isoformat()
        os.environ["LUCID_ACCESS_TOKEN_EXPIRY"] = expiry
        save_secret("lucid_access_token", access_token)
    if refresh_token:
        os.environ["LUCID_REFRESH_TOKEN"] = refresh_token
        save_secret("lucid_refresh_token", refresh_token)


def _is_token_expired() -> bool:
    """Return True if the stored access token is missing or about to expire."""
    expiry_str = os.environ.get("LUCID_ACCESS_TOKEN_EXPIRY")
    token      = os.environ.get("LUCID_ACCESS_TOKEN")
    if not token:
        return True
    if not expiry_str:
        return False  # token exists but no expiry info — assume valid
    try:
        return datetime.fromisoformat(expiry_str) <= datetime.utcnow()
    except ValueError:
        return False


def _refresh_access_token():
    """Use the stored refresh_token to obtain a new access + refresh token pair.
    Per Lucid docs: refreshing invalidates the old tokens — both must be saved.
    Requires offline_access scope.
    """
    refresh_token = (os.environ.get("LUCID_REFRESH_TOKEN") or "").strip()
    if not refresh_token:
        raise ValueError("No refresh token available. Re-authorize via /auth/lucidchart")

    client_secret = (os.environ.get("LUCID_CLIENT_SECRET", LUCID_CLIENT_SECRET) or "").strip()
    if not client_secret:
        raise ValueError("LUCID_CLIENT_SECRET env var not set")

    # Lucid requires JSON body, NOT form-encoded
    resp = http_requests.post(_LUCID_TOKEN_URL, json={
        "grant_type":     "refresh_token",
        "refresh_token":  refresh_token,
        "client_id":      _LUCID_CLIENT_ID,
        "client_secret":  client_secret,
    }, timeout=30)

    if not resp.ok:
        raise RuntimeError(f"Token refresh failed {resp.status_code}: {resp.text}")

    tokens = resp.json()
    _save_tokens(tokens)
    log.info("[OAuth] Access token refreshed successfully.")
    return tokens



def _get_valid_access_token() -> str:
    """Return a valid access token, auto-refreshing if expired."""
    if _is_token_expired():
        log.info("[OAuth] Access token expired or missing — attempting refresh.")
        try:
            _refresh_access_token()
        except Exception as e:
            log.warning("[OAuth] Auto-refresh failed: %s", e)
    return os.environ.get("LUCID_ACCESS_TOKEN", LUCIDCHART_API_TOKEN)


def _exchange_code_for_tokens(code):
    """Exchange an OAuth2 authorization code for access + refresh tokens.
    Per Lucid docs: POST with JSON body to https://api.lucid.co/oauth2/token
    """
    client_secret = (os.environ.get("LUCID_CLIENT_SECRET", LUCID_CLIENT_SECRET) or "").strip()
    if not client_secret:
        raise ValueError("LUCID_CLIENT_SECRET env var not set")

    log.info("CID=%s", _LUCID_CLIENT_ID)
    log.info("REDIRECT=%s", _LUCID_REDIRECT)
    log.info("ENV_CID=%s", os.environ.get("LUCID_CLIENT_ID"))
    log.info("ENV_SECRET_PRESENT=%s", bool(os.environ.get("LUCID_CLIENT_SECRET")))
    log.info("SECRET_LEN=%s", len(client_secret))
    log.info("CODE_LEN=%s", len(code.strip()) if code else 0)

    resp = http_requests.post(_LUCID_TOKEN_URL, json={
        "grant_type":    "authorization_code",
        "code":          code.strip(),
        "redirect_uri":  _LUCID_REDIRECT,
        "client_id":     _LUCID_CLIENT_ID,
        "client_secret": client_secret,
    }, timeout=30)

    if not resp.ok:
        raise RuntimeError(f"Token exchange failed {resp.status_code}: {resp.text}")

    tokens = resp.json()
    _save_tokens(tokens)
    log.info("[OAuth] LucidChart tokens stored in environment and Secret Manager.")
    return tokens

@app.route("/auth/lucidchart")
def auth_lucidchart():
    """
    Auth dashboard:
      • Shows current token status
      • Provides an 'Authorize' link to start the OAuth2 consent flow
      • Has a form to paste the authorization code (shown at Lucid's redirect page)
      • Has a form to paste an access token directly
    """
    params = {
        "response_type": "code",
        "client_id":     _LUCID_CLIENT_ID,
        "redirect_uri":  _LUCID_REDIRECT,
        "scope":         SCOPES,
        "state":         "lucid-auth",
    }
    auth_url = _LUCID_AUTH_URL + "?" + urllib.parse.urlencode(params)

    existing_token = os.environ.get("LUCID_ACCESS_TOKEN", "")
    token_status   = (existing_token[:16] + "…  ✅ set") if existing_token else "❌ not set"
    refresh_status = ("✅ set" if os.environ.get("LUCID_REFRESH_TOKEN") else "❌ not set")

    html = f"""<!DOCTYPE html>
<html><head><title>LucidChart Auth</title>
<style>
  body {{font-family:sans-serif;max-width:640px;margin:40px auto;padding:0 16px}}
  h2  {{border-bottom:1px solid #ccc;padding-bottom:8px}}
  .card {{background:#f9f9f9;border:1px solid #ddd;border-radius:6px;padding:16px;margin:16px 0}}
  .ok  {{color:green}} .err{{color:red}}
  input[type=text],input[type=password]{{width:100%;box-sizing:border-box;padding:6px;margin:6px 0}}
  button{{padding:8px 18px;cursor:pointer}}
  a.btn{{display:inline-block;padding:8px 18px;background:#4c6ef5;color:#fff;border-radius:4px;text-decoration:none}}
</style></head><body>
<h2>LucidChart OAuth Status</h2>
<div class="card">
  <b>Access token:</b>  <span class="{'ok' if existing_token else 'err'}">{token_status}</span><br>
  <b>Refresh token:</b> <span class="{'ok' if os.environ.get('LUCID_REFRESH_TOKEN') else 'err'}">{refresh_status}</span>
</div>

<div class="card">
  <h3>Step 1 — Authorize with LucidChart</h3>
  <p>Click below. LucidChart will ask you to log in, then redirect to a Lucid page that
  <b>displays your authorization code</b>. Copy that code and paste it in Step 2.</p>
  <a class="btn" href="{auth_url}" target="_blank">Open LucidChart consent ↗</a>
</div>

<div class="card">
  <h3>Step 2 — Paste the authorization code</h3>
  <form method="POST" action="/auth/lucidchart/exchange-code">
    <input type="text" name="code" placeholder="Paste authorization code here…" required>
    <button type="submit">Exchange for tokens</button>
  </form>
</div>

<div class="card">
  <h3>Alternative A — Refresh Token</h3>
  <p>If you have previously authorized and have a refresh token stored, click below to get a new access token without re-authorizing. Tokens auto-refresh on every API call too.</p>
  <form method="POST" action="/auth/lucidchart/refresh">
    <button type="submit">Refresh Access Token</button>
  </form>
</div>

<div class="card">
  <h3>Alternative B — Paste an access token directly</h3>
  <p>If you already have a valid token from the LucidChart developer portal:</p>
  <form method="POST" action="/auth/lucidchart/set-token">
    <input type="password" name="access_token"  placeholder="Access token"  required>
    <input type="text"     name="refresh_token" placeholder="Refresh token (optional)">
    <button type="submit">Save token</button>
  </form>
</div>
</body></html>"""
    return html


@app.route("/auth/lucidchart/refresh", methods=["GET", "POST"])
def auth_lucidchart_refresh():
    """Manually trigger a token refresh using the stored refresh token."""
    try:
        tokens = _refresh_access_token()
    except (ValueError, RuntimeError) as exc:
        log.error("[OAuth] refresh failed: %s", exc)
        return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>❌ Token Refresh Failed</h2>
<p><b>Error:</b> {exc}</p>
<p>You may need to re-authorize via Step 1 above.</p>
<a href="/auth/lucidchart">← Back to auth page</a>
</body></html>""", 502

    at = tokens.get("access_token", "")
    return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>✅ Token Refreshed</h2>
<p><b>New access token:</b> {at[:16]}…</p>
<p>expires_in = {tokens.get('expires_in')} s</p>
<a href="/auth/lucidchart">← Back to auth page</a>
</body></html>"""

@app.route("/auth/lucidchart/exchange-code", methods=["POST"])
def auth_lucidchart_exchange_code():
    """Accept a manually pasted authorization code and exchange it for tokens."""
    code = request.form.get("code") or (request.json or {}).get("code")
    if not code:
        return jsonify({"status": "error", "detail": "no code provided"}), 400
    try:
        tokens = _exchange_code_for_tokens(code.strip())
    except (ValueError, RuntimeError) as exc:
        log.error("[OAuth] exchange-code failed: %s", exc)
        return jsonify({"status": "error", "detail": str(exc)}), 502

    at = tokens.get("access_token", "")
    rt = tokens.get("refresh_token", "")
    # Redirect back to the auth dashboard with confirmation
    return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>✅ Tokens saved</h2>
<p><b>Access token:</b>  {at[:16]}…</p>
<p><b>Refresh token:</b> {rt[:16] + '…' if rt else '(none)'}</p>
<p>expires_in = {tokens.get('expires_in')} s</p>
<a href="/auth/lucidchart">← Back to auth page</a>
</body></html>"""


@app.route("/auth/lucidchart/set-token", methods=["POST"])
def auth_lucidchart_set_token():
    """Directly inject an access token (and optional refresh token) into the environment."""
    body          = request.form if request.form else (request.get_json() or {})
    access_token  = body.get("access_token", "").strip()
    refresh_token = body.get("refresh_token", "").strip()

    if not access_token:
        return jsonify({"status": "error", "detail": "access_token is required"}), 400

    _save_tokens({"access_token": access_token, "refresh_token": refresh_token})
    log.info("[OAuth] Access token manually set & saved to Secret Manager.")

    return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>✅ Token saved</h2>
<p><b>Access token:</b>  {access_token[:16]}…</p>
<p><b>Refresh token:</b> {refresh_token[:16] + '…' if refresh_token else '(none)'}</p>
<a href="/auth/lucidchart">← Back to auth page</a>
</body></html>"""


@app.route("/auth/lucidchart/callback")
def auth_lucidchart_callback():
    """
    Standard OAuth2 callback — handles ?code= if LucidChart ever redirects here directly.
    Also accepts ?code= as a fallback for manual redirect.
    """
    code  = request.args.get("code")
    error = request.args.get("error")

    if error or not code:
        msg = error or "no code returned"
        log.error("[OAuth] Callback error: %s", msg)
        return redirect(f"/auth/lucidchart?error={urllib.parse.quote(msg)}")

    try:
        tokens = _exchange_code_for_tokens(code)
    except (ValueError, RuntimeError) as exc:
        log.error("[OAuth] Callback token exchange failed: %s", exc)
        return jsonify({"status": "error", "detail": str(exc)}), 502

    at = tokens.get("access_token", "")
    return f"""<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:480px;margin:40px auto">
<h2>✅ LucidChart authorized</h2>
<p><b>Access token:</b>  {at[:16]}…</p>
<p>expires_in = {tokens.get('expires_in')} s</p>
<a href="/">← Home</a>
</body></html>"""


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


