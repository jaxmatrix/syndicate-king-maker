#!/usr/bin/env python3
"""
Syndicate Background Queue Worker Daemon.
Polls Helix /api/simulations on syndicate-app.jai.allr.work for pending requests,
executes the full SyndicateGraphEngine (Anakin Wire, Google Places, Hotspots),
and updates the record with the completed result payload.
"""

import os
import sys
import time
import json
import uuid
import logging
import urllib.request
import urllib.error

sys.path.insert(0, '/opt/data')
sys.path.insert(0, '/opt/data/syndicate/backend')

from engine import SyndicateGraphEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [syndicate_worker] %(message)s")
logger = logging.getLogger("syndicate_worker")

HELIX_URL = os.environ.get("HELIX_GATEWAY_URL", "http://helix:8080").rstrip("/")
APP_HOST = "syndicate-app.jai.allr.work"

engine = SyndicateGraphEngine()
processed_ids = set()

def fetch_pending_simulations():
    url = f"{HELIX_URL}/api/simulations"
    headers = {"Host": APP_HOST, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            items = data if isinstance(data, list) else data.get("data", [])
            return [it for it in items if it.get("status") == "pending" and it.get("id") not in processed_ids]
    except Exception as e:
        logger.debug(f"Fetch error: {e}")
        return []

def complete_simulation(task_id, user_id, company_name, payload, result):
    # In Helix API, we post a completed record or update
    url = f"{HELIX_URL}/api/simulations"
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
        logger.error(f"Error publishing completed simulation: {e}")

def run_worker_loop():
    logger.info("Starting Syndicate Worker loop...")
    while True:
        try:
            tasks = fetch_pending_simulations()
            for t in tasks:
                task_id = t.get("id")
                processed_ids.add(task_id)
                logger.info(f"Processing simulation request {task_id} for {t.get('company_name')}")
                try:
                    payload = json.loads(t.get("payload", "{}"))
                except Exception:
                    payload = {}
                
                # Execute full simulation
                try:
                    res = engine.execute_syndicate_simulation(payload)
                    complete_simulation(task_id, t.get("user_id", "guest"), t.get("company_name", ""), payload, res)
                except Exception as ex:
                    logger.error(f"Error running simulation for {task_id}: {ex}")
        except Exception as e:
            logger.error(f"Worker loop exception: {e}")
        time.sleep(1.0)

if __name__ == "__main__":
    run_worker_loop()
