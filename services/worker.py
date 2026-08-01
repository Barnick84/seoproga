import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

import pymysql

logger = logging.getLogger(__name__)

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

from config import Config  # noqa: E402

PYTHON_PATH = sys.executable

SCRIPTS_DIR = os.path.join(project_root, "scripts")


def fetch_and_schedule_tasks(limit: int = 5):
    conn = Config.get_conn()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    tasks = []
    try:
        conn.begin()
        cur.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED",
            (limit,),
        )
        pending = cur.fetchall()
        for task in pending:
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
        logger.warning("Error fetching tasks: %s", e)
        return []
    finally:
        cur.close()
        conn.close()


active_processes = []
processes_lock = threading.Lock()
task_retries = {}
MAX_RETRIES = 3
_shutdown = threading.Event()


def _cleanup_children():
    with processes_lock:
        for proc, _ in active_processes:
            try:
                proc.terminate()
            except Exception:
                pass
        active_processes.clear()


def _signal_handler(signum, frame):
    logger.info("Received signal %s, shutting down...", signum)
    _shutdown.set()
    _cleanup_children()
    sys.exit(0)


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


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
        logger.warning("Failed to update task %s status: %s", task_id, e)


def _build_task_args(
    task_type: str, payload: dict, user_id: int, task_id: int, script_path: str
) -> list[str]:
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
        cluster_id = payload.get("cluster_id") or payload.get("clusterId") or "None"
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
    return args


def run_task(task: dict) -> None:
    task_id = task["id"]
    user_id = task["user_id"]
    task_type = task["task_type"]
    payload = json.loads(task["payload"]) if isinstance(task["payload"], str) else task["payload"]

    logger.info("Starting task %s (%s) for user %s", task_id, task_type, user_id)

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
        logger.error("Unknown task type: %s", task_type)
        _update_task_status(task_id, "failed", f"Unknown task type: {task_type}")
        return

    _update_task_status(task_id, "running")

    args = _build_task_args(task_type, payload, user_id, task_id, script_path)

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root
        proc = subprocess.Popen(args, cwd=project_root, env=env)
        with processes_lock:
            active_processes.append((proc, task))
    except Exception as e:
        logger.warning("Failed to spawn task %s: %s", task_id, e)
        _update_task_status(task_id, "failed", str(e))


def _handle_finished_process(proc, task: dict) -> None:
    rc = proc.returncode
    task_id = task["id"]
    logger.info("Task %s completed with code %s", task_id, rc)

    with processes_lock:
        if (proc, task) in active_processes:
            active_processes.remove((proc, task))

    if rc == 0:
        _update_task_status(task_id, "completed")
        task_retries.pop(task_id, None)
        return

    retries = task_retries.get(task_id, 0)
    if retries < MAX_RETRIES:
        task_retries[task_id] = retries + 1
        logger.warning(
            "Task %s failed (code %s). Retrying (%s/%s)...",
            task_id,
            rc,
            retries + 1,
            MAX_RETRIES,
        )
        _update_task_status(task_id, "scheduled", f"Retry {retries + 1}/{MAX_RETRIES}")
        run_task(task)
    else:
        _update_task_status(task_id, "failed", f"Exit code {rc} after {MAX_RETRIES} retries")
        task_retries.pop(task_id, None)


def main() -> None:
    logger.info("SEO Worker started (PID: %s)", os.getpid())
    while not _shutdown.is_set():
        try:
            with processes_lock:
                current_processes = active_processes[:]
            for proc, task in current_processes:
                if proc.poll() is not None:
                    _handle_finished_process(proc, task)

            with processes_lock:
                active_count = len(active_processes)
            if active_count < 5 and not _shutdown.is_set():
                tasks = fetch_and_schedule_tasks(5 - active_count)
                for task in tasks:
                    run_task(task)
            time.sleep(2)
        except Exception as e:
            logger.warning("Worker loop error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
