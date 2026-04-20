# Capstone-ProjectTeam3

## Project Overview
This project is an automated Active Directory to cloud security data pipeline developed for our capstone project.

The pipeline is designed to:
- extract Active Directory data using PowerShell
- stage and process the data in Google BigQuery
- run cloud-side processing with Python
- support relationship visualization for security analysis

## Repository Structure
```text
Capstone-ProjectTeam3/
├── ActiveDirectoryScript/
│   └── main.ps1
├── CloudRunFunction/
│   ├── Dockerfile
│   ├── bq_manager.py
│   ├── lucidchart_builder.py
│   ├── lucidchart_display.py
│   ├── main.py
│   └── requirements.txt
└── README.md

**Technologies Used: **
1. PowerShell
2. Python
3. Google BigQuery
4. Google Cloud Run
5. Docker
6. Lucid / Lucidchart

**Prerequisites**
Before running this project, make sure you have:
1. Windows PowerShell
2. Python 3.10 or later
3. pip
4. Docker 
5. Google Cloud access configured
6. BigQuery dataset/project access
7. Any required API credentials or environment variables for your setup

**How to Run the Project**
1. Run the Active Directory extraction script
Open PowerShell and run:
cd ActiveDirectoryScript
.\main.ps1

2. Run the CloudRunFunction locally
Open a terminal and run:
cd CloudRunFunction
python -m venv .venv
Activate the virtual environment:
Windows
.venv\Scripts\activate
macOS/Linux
source .venv/bin/activate

**Install the dependencies:**
pip install -r requirements.txt

Run the Python application:
python main.py
Run with Docker

From the CloudRunFunction folder:
docker build -t capstone-cloudrun .
docker run -p 8080:8080 capstone-cloudrun

**Notes**
Update all required credentials, tokens, and environment variables before running.
Some features may depend on access to Google Cloud services and external APIs.
We are still working on our project Finalization.

**TEAM 3**
Shahiba Shamshad
Michael Butler
Mounia Touil
Koko Afantchao
