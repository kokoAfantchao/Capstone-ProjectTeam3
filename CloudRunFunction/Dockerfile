# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# BigQuery configuration — override these at deploy time via Cloud Run env vars
ENV BQ_PROJECT="ksu-team-2"
ENV BQ_DATASET="capstone_dev"
# or "local_dev" for local testing
ENV RUN_ENV="production"  

# LucidChart configuration — override these at deploy time via Cloud Run env vars
ENV LUCIDCHART_API_TOKEN=""
ENV LUCIDCHART_DOCUMENT_ID=""

# LucidChart OAuth / import credentials
ENV LUCID_ACCESS_TOKEN=""
ENV LUCID_CLIENT_ID="NEhXzDpgVSIhQKJSXzFyG0rJYshiuh5rfHfevyz1"
ENV LUCID_CLIENT_SECRET="_-RBdkkEmu-C0FRb6IXHltrnV3BPxUKq5HRQZg-pD63_1viQcw_8mVAc50ZdTHaRer_Gkr794qaKSte51oGg"
ENV LUCID_REFRESH_TOKEN=""

# BigQuery views used by lucidchart_builder.py
ENV NODES_VIEW="vw_lucid_nodes_all"
ENV EDGES_VIEW="vw_lucid_edges_all"

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
