# services/worker.py
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

import pymysql

if sys.platform == "win32" and "pytest" not in sys.modules:
    import io

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config

PYTHON_PATH = sys.executable

SCRIPTS_DIR = os.path.join(project_root, "scripts")


def fetch_and_schedule_tasks(limit: int = 5):
    conn = Config.get_conn()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    tasks = []
    try:
        conn.start_transaction()
        for _ in range(limit):
            cur.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1")
            task = cur.fetchone()
            if not task:
                break

            cur.execute(
                "UPDATE tasks SET status = 'scheduled' WHERE id = %s AND status = 'pending'",
                (task["id"],),
            )
            if cur.rowcount > 0:
                tasks.append(task)

        conn.commit()
        return tasks
    except Exception as e:
        conn.rollback()
        print(f"Error fetching tasks: {e}")
        return []
    finally:
        cur.close()
        conn.close()


active_processes = []
processes_lock = threading.Lock()
task_retries = {}
MAX_RETRIES = 3


def _update_task_status(task_id: int, status: str, error: str | None = None) -> None:
    try:
        conn = Config.get_conn()
        cur = conn.cursor()
        try:
            if status == "running":
                cur.execute(
                    "UPDATE tasks SET status = %s, started_at = %s WHERE id = %s",
                    (status, datetime.now(), task_id),
                )
            elif status == "failed":
                cur.execute(
                    "UPDATE tasks SET status = %s, finished_at = %s, error = %s WHERE id = %s",
                    (status, datetime.now(), error or "Process failed", task_id),
                )
            else:
                cur.execute(
                    "UPDATE tasks SET status = %s, finished_at = %s WHERE id = %s",
                    (status, datetime.now(), task_id),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"Failed to update task {task_id} status: {e}")


def run_task(task: dict) -> None:
    task_id = task["id"]
    user_id = task["user_id"]
    task_type = task["task_type"]
    payload = json.loads(task["payload"]) if isinstance(task["payload"], str) else task["payload"]

    print(f"[{datetime.now()}] Starting task {task_id} ({task_type}) for user {user_id}")

    script_map = {
        "frequency": os.path.join(SCRIPTS_DIR, "fetch_frequency.py"),
        "clustering": os.path.join(SCRIPTS_DIR, "run_clustering.py"),
        "mapping": os.path.join(SCRIPTS_DIR, "run_mapping.py"),
        "competitor_analysis": os.path.join(SCRIPTS_DIR, "run_competitor_analysis.py"),
        "fetch_queries": os.path.join(SCRIPTS_DIR, "fetch_yandex_queries.py"),
        "seo_pipeline": os.path.join(SCRIPTS_DIR, "run_seo_pipeline.py"),
    }

    script_path = script_map.get(task_type)
    if not script_path:
        print(f"Unknown task type: {task_type}")
        _update_task_status(task_id, "failed", f"Unknown task type: {task_type}")
        return

    _update_task_status(task_id, "running")

    domain = payload.get("domain", "")
    args = [PYTHON_PATH, script_path]

    if task_type == "frequency":
        args.extend(
            [
                domain,
                str(user_id),
                payload.get("device", ""),
                payload.get("region", ""),
                payload.get("mode", "all"),
                str(payload.get("minFrequency", 10)),
                str(task_id),
                str(payload.get("clusterId", 0)),
            ]
        )
    elif task_type == "clustering":
        args.extend([domain, str(user_id), str(task_id)])
    elif task_type == "mapping":
        args.extend([domain, str(user_id), "None", str(task_id)])
    elif task_type == "competitor_analysis":
        cluster_id = payload.get("cluster_id", payload.get("clusterId", ""))
        args.extend([domain, str(user_id), str(cluster_id), str(task_id)])
    elif task_type == "fetch_queries":
        args.extend([domain, str(user_id)])
    elif task_type == "seo_pipeline":
        cluster_id = payload.get("cluster_id", payload.get("clusterId", 0))
        target_url = payload.get("target_url", payload.get("targetUrl", "None")) or "None"
        region = payload.get("region", "213")
        head_query = payload.get("head_query", payload.get("headQuery", "None")) or "None"
        args.extend(
            [
                domain,
                str(user_id),
                str(cluster_id),
                str(task_id),
                str(target_url),
                str(region),
                str(head_query),
            ]
        )

    try:
        proc = subprocess.Popen(args, cwd=project_root)
        with processes_lock:
            active_processes.append((proc, task))
    except Exception as e:
        print(f"Failed to spawn task {task_id}: {e}")
        _update_task_status(task_id, "failed", str(e))


def main() -> None:
    print(f"SEO Worker started (PID: {os.getpid()})")
    while True:
        try:
            with processes_lock:
                current_processes = active_processes[:]
            for proc, task in current_processes:
                if proc.poll() is not None:
                    rc = proc.returncode
                    task_id = task["id"]
                    print(f"[{datetime.now()}] Task {task_id} completed with code {rc}")

                    with processes_lock:
                        if (proc, task) in active_processes:
                            active_processes.remove((proc, task))

                    if rc == 0:
                        _update_task_status(task_id, "completed")
                        if task_id in task_retries:
                            del task_retries[task_id]
                    else:
                        retries = task_retries.get(task_id, 0)
                        if retries < MAX_RETRIES:
                            task_retries[task_id] = retries + 1
                            print(
                                f"[{datetime.now()}] Task {task_id} failed (code {rc}). Retrying ({retries + 1}/{MAX_RETRIES})..."
                            )
                            _update_task_status(
                                task_id, "scheduled", f"Retry {retries + 1}/{MAX_RETRIES}"
                            )
                            # Re-run immediately or let it be picked up? We can just call run_task(task)
                            run_task(task)
                        else:
                            _update_task_status(
                                task_id, "failed", f"Exit code {rc} after {MAX_RETRIES} retries"
                            )
                            if task_id in task_retries:
                                del task_retries[task_id]

            with processes_lock:
                active_count = len(active_processes)
            if active_count < 5:
                tasks = fetch_and_schedule_tasks(5 - active_count)
                for task in tasks:
                    run_task(task)
            time.sleep(2)
        except Exception as e:
            print(f"Worker loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
