#!/usr/bin/env python3
"""
Syndicate Background Research Worker Daemon.
Polls the Helix research-run queue for pending requests, executes the full
SyndicateGraphEngine research pipeline (Anakin search + Reddit Wire reads +
Google Places + centroid hotspots), and publishes the completed result.
"""

import os
import sys
import time
import json
import uuid
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')

from engine import SyndicateGraphEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [syndicate_worker] %(message)s")
logger = logging.getLogger("syndicate_worker")

HELIX_URL = os.environ.get("HELIX_GATEWAY_URL", "http://helix:8080").rstrip("/")
APP_HOST = "syndicate-app.jai.allr.work"

# The queue endpoint. /api/research-runs is the current name; /api/simulations is
# the legacy alias and still works, so this can be flipped back if ever needed.
QUEUE_PATH = os.environ.get("SYNDICATE_QUEUE_PATH", "/api/research-runs")

# How many research runs to execute at once. Runs are I/O-bound, so a small pool
# keeps a backlog from serialising behind a single slow run.
MAX_CONCURRENCY = int(os.environ.get("SYNDICATE_WORKER_CONCURRENCY", "3"))

# Only claim pending rows newer than this. Completion is published as a NEW row
# (status done:<id>) rather than updating the original, so the original stays
# "pending" forever - without a freshness window every worker restart would
# re-run the entire historical backlog.
MAX_PENDING_AGE_S = int(os.environ.get("SYNDICATE_PENDING_MAX_AGE_S", "1800"))

engine = SyndicateGraphEngine()
processed_ids = set()

def _is_fresh(row) -> bool:
    """True when a pending row is recent enough to be worth running."""
    raw = str(row.get("created_at") or "")
    if not raw:
        # No timestamp: only trust it if we have not seen the id before.
        return False
    try:
        stamp = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return False
    age = (datetime.now(timezone.utc) - stamp).total_seconds()
    return 0 <= age <= MAX_PENDING_AGE_S


def fetch_pending_runs():
    url = f"{HELIX_URL}{QUEUE_PATH}"
    headers = {"Host": APP_HOST, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            items = data if isinstance(data, list) else data.get("data", [])
            return [it for it in items
                    if it.get("status") == "pending"
                    and it.get("id") not in processed_ids
                    and _is_fresh(it)]
    except Exception as e:
        logger.debug(f"Fetch error: {e}")
        return []

def complete_run(task_id, user_id, company_name, payload, result):
    # In Helix API, we post a completed record or update
    url = f"{HELIX_URL}{QUEUE_PATH}"
    headers = {"Host": APP_HOST, "Content-Type": "application/json"}
    update_data = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "company_name": company_name,
        "payload": json.dumps(payload) if isinstance(payload, dict) else str(payload),
        "result": json.dumps(result) if isinstance(result, dict) else str(result),
        "status": f"done:{task_id}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    try:
        post_req = urllib.request.Request(url, data=json.dumps(update_data).encode("utf-8"), headers=headers, method="POST")
        urllib.request.urlopen(post_req, timeout=5)
        logger.info(f"Published completed result for task {task_id}")
    except Exception as e:
        logger.error(f"Error publishing completed research run: {e}")

def publish_progress(task_id, user_id, company_name, label):
    """
    Publish one action line for a run in progress.

    Progress is published as its own append-only queue record (status
    'progress:<taskId>') because the queue offers no update operation. The client
    polls and renders these in order, so the chat log shows every action the run
    actually performs instead of a silent spinner.
    """
    url = f"{HELIX_URL}{QUEUE_PATH}"
    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user_id or "guest",
        "company_name": company_name or "",
        "payload": "{}",
        "result": label,
        "status": f"progress:{task_id}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Host": APP_HOST, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        logger.info(f"[{task_id[:8]}] {label}")
    except Exception as e:
        logger.debug(f"progress publish failed: {e}")


def process_task(t, task_id):
    """Execute one queued research run and publish its result."""
    logger.info(f"Processing research request {task_id} for {t.get('company_name')}")
    try:
        payload = json.loads(t.get("payload", "{}"))
    except Exception:
        payload = {}

    user_id = t.get("user_id", "guest")
    company_name = t.get("company_name", "")

    def on_progress(label):
        publish_progress(task_id, user_id, company_name, label)

    try:
        res = engine.execute_research_run(payload, progress=on_progress)
        complete_run(task_id, user_id, company_name, payload, res)
    except Exception as ex:
        logger.error(f"Error running research pipeline for {task_id}: {ex}")
        publish_progress(task_id, user_id, company_name, f"Scan failed · {ex}")


def run_worker_loop():
    logger.info(f"Starting Syndicate research worker loop (queue: {QUEUE_PATH}, "
                f"concurrency: {MAX_CONCURRENCY})...")
    # A run is I/O-bound (Anakin search/scrape + LLM + Places), so a small thread
    # pool materially improves throughput and stops a queue backlog from delaying
    # later requests behind earlier ones. Persistence is a plain append, so
    # concurrent publishes stay safe.
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        while True:
            try:
                tasks = fetch_pending_runs()
                for t in tasks:
                    task_id = t.get("id")
                    processed_ids.add(task_id)
                    pool.submit(process_task, t, task_id)
            except Exception as e:
                logger.error(f"Worker loop exception: {e}")
            time.sleep(1.0)

if __name__ == "__main__":
    run_worker_loop()
