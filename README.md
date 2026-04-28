# Capstone Project — Team 3

## Project Overview

This project is an automated **Active Directory to Cloud Security Data Pipeline** built as part of our capstone project.

The pipeline extracts Active Directory data from a Windows environment, stages it in Google BigQuery, and makes it available for security analysis and relationship visualization through a cloud-hosted Flask service that integrates with LucidChart.

**The pipeline flow:**

```
Active Directory (Windows)
        │
        ▼
  PowerShell ( Export / main.ps1 CLI  and AD_Export.ps1  to extract AD, DHCP, DNS data into JSON files )
        │  
        ▼
  Google BigQuery (tables & views)
        │
        ▼
  Cloud Run Flask Service (CloudRunFunction)
        │
        ▼
  LucidChart Diagram (nodes & edges visualization)
```

**Technologies used:**

| Layer | Technology |
|---|---|
| Data extraction | PowerShell, ActiveDirectory module |
| Data storage | Google BigQuery |
| Cloud service | Google Cloud Run, Python 3, Flask || Containerization | Docker |
| Visualization | LucidChart API |
| Secret management | Google Cloud Secret Manager |

---

## Team 3

| Name | Role |
|---|---|
| Shahiba Shamshad | Team Member |
| Michael Butler | Team Member |
| Mounia Touil | Team Member |
| Koko Afantchao | Team Member |

---

## Project Architecture

The project is split into two independent but connected workflows:

### 1. Active Directory Export (on-premise / Windows)

- [AD_Export.ps1](AD_Export.ps1) performs a comprehensive export of AD, DHCP, and DNS data and writes structured JSON output files.
- [ActiveDirectoryScript/main.ps1](ActiveDirectoryScript/main.ps1) is a CLI wrapper that automates environment setup, data extraction, and pushing JSON files to BigQuery.

### 2. Cloud Run Visualization Service

- [CloudRunFunction/main.py](CloudRunFunction/main.py) is a Flask HTTP service deployed to Google Cloud Run.
- It reads BigQuery tables/views, listens for trigger events, and calls the LucidChart API to build or update diagrams.

**Data flow summary:**

```
main.ps1 (setup + push-data)
    └─► BigQuery tables
            └─► Flask /eventlistener endpoint
                    └─► lucidchart_builder.py
                            └─► LucidChart document
```

---

## Code Structure

```text
Capstone-ProjectTeam3/
├── ActiveDirectoryScript/
│   ├── main.ps1                       # CLI: setup, extract-data, push-data, sync
|   ├── AD_Export.ps1                      # Full AD/DHCP/DNS exporter (PowerShell)
│   ├── data_files/                    # JSON export output (generated, not committed)
|
└── CloudRunFunction/
    ├── main.py                        # Flask app entry point
    ├── bq_manager.py                  # BigQuery client and query utilities
    ├── lucidchart_builder.py          # Builds and imports LucidChart documents
    ├── lucidchart_display.py          # LucidChart display/token helpers
    ├── Dockerfile                     # Container definition for Cloud Run
    └── requirements.txt               # Python dependencies
```

---

## Setup: ActiveDirectoryScript

### Requirements

- Windows machine joined to the Active Directory domain.
- PowerShell with permission to execute scripts ad Admin.
- Google Cloud project with BigQuery dataset already created.
- Service account key JSON placed at  same path level as the main.ps1 script
- activity.log file with the same path level as the main.ps1 script( used for logging the events of the script)
### Running the CLI script

```powershell
cd ActiveDirectoryScript

# First-time setup: installs portable Python and gcloud CLI
powershell -ExecutionPolicy Bypass -File .\main.ps1 setup

# Extrat and Push latest JSON files to BigQuery
powershell -ExecutionPolicy Bypass -File .\main.ps1 sync ( just ./main.ps1 will also work as sync is the default command) 

**Interactive mode** — :
Available commands: `setup`, `extract-data`, `push-data`, `sync`, `clean-up`, `help`.

### Extracting AD  and syncing with BigQuery on a schedule 
Use Windows Task Scheduler to run `main.ps1 ` at your desired frequency (e.g. daily, weekly). This will automate the data extraction and BigQuery upload process.
---

## Setup: CloudRunFunction

### Requirements
- Docker (for containerized deployment)
- `gcloud` CLI authenticated with your Google Cloud project
- The following GCP APIs enabled:
  - `run.googleapis.com`
  - `cloudbuild.googleapis.com`
  - `artifactregistry.googleapis.com`
- A runtime service account with:
  - BigQuery Job User
  - BigQuery Data Viewer
  - Secret Manager Accessor (if using secrets for credentials)
  - event trigger permissions (if using Pub/Sub or Cloud Scheduler)
  - build permissions (if deploying from source with Cloud Build)

### Deploy to Cloud Run (Web Interface)

To deploy the service manually using the Google Cloud Console:

1. **Build the Container Image (if not deploying from source):**
   - Submit your code to Artifact Registry via Cloud Build, or directly from GitHub using Cloud Runs integrated "Connect repo" setup.
2. Go to the **Google Cloud Console** web interface and navigate to **Cloud Run**.
3. Click the **Create Service** button.
4. **Deploy Source:**
   - Choose **Continuously deploy new revisions from a source repository**, connect to the GitHub repo, and choose the `CloudRunFunction` folder as your Build Context.
   - *Or* select **Deploy one revision from an existing container image** and select your Artifact Registry image.
5. **Service Name:** Enter `capstone-cloudrun`
7d. **Authentication:** Select **Allow unauthenticated invocations**.
8. **Container, Variables & Secrets, Connections, Security** (expand to configure):
   - **Container port:** `8080` (default for Flask apps/Dockerfiles if not specified).
   - **Environment Variables** (add each key/value):
     - `RUN_ENV` = `production`
     - `BQ_PROJECT` = `YOUR_PROJECT_ID`
     - `BQ_DATASET` = `YOUR_DATASET`
     - `NODES_VIEW` = `vw_lucid_nodes_all`
     - `EDGES_VIEW` = `vw_lucid_edges_all`
   - **Security / Service Account:** Select your specialized runtime service account (e.g., `YOUR_RUNTIME_SA@...`) that has BigQuery access.
9. Click **Create**. Once completed, Cloud Run will display the auto-generated live URL endpoint for your service.

### Required environment variables
 this need to be set in the Dockerfile or in the Cloud Run environment variable settings, but make sure to use Google Cloud Secret Manager for sensitive values like API tokens and service account keys.

| Variable | Description |
|---|---|
| `RUN_ENV` | `production` or `local_dev` |
| `BQ_PROJECT` | Google Cloud project ID |
| `BQ_DATASET` | BigQuery dataset name |
| `NODES_VIEW` | BigQuery view for LucidChart nodes |
| `EDGES_VIEW` | BigQuery view for LucidChart edges |
| `LUCIDCHART_API_TOKEN` | LucidChart API token |
| `LUCIDCHART_DOCUMENT_ID` | Target LucidChart document ID |
| `LUCID_CLIENT_ID` | OAuth client ID (if using OAuth flow) |
| `LUCID_CLIENT_SECRET` | OAuth client secret |
| `LUCID_REFRESH_TOKEN` | OAuth refresh token |

> Store all sensitive values in **Google Cloud Secret Manager** rather than plain environment variables.

### Service endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Dashboard table view |
| `/big-querry/eventlistener` | POST | Triggers LucidChart import |
| `/lucidcharts-history` | GET | Import history page |
| `/auth/lucidchart` | GET | OAuth helper UI |

---

## Security Notes

- Never commit `service-account.json` or any API token to source control.
- Keep generated export files and logs out of version control (see [.gitignore](.gitignore)).
- Use Google Cloud Secret Manager to securely store and access sensitive credentials.
- Ensure least privilege for service accounts and API permissions.

