# services/worker.py
import sys
import os
import time
import json
import subprocess
from datetime import datetime

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config

PYTHON_PATH = sys.executable

SCRIPTS_DIR = os.path.join(project_root, 'nodejs-app', 'scripts')


def get_pending_tasks():
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT 5")
        return cur.fetchall()
    finally:
        conn.close()


def _mark_scheduled(task_id: int) -> None:
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE tasks SET status = 'scheduled' WHERE id = %s", (task_id,))
        conn.commit()
    finally:
        conn.close()


def run_task(task: dict) -> None:
    task_id = task['id']
    user_id = task['user_id']
    task_type = task['task_type']
    payload = json.loads(task['payload']) if isinstance(task['payload'], str) else task['payload']

    print(f"[{datetime.now()}] Starting task {task_id} ({task_type}) for user {user_id}")

    script_map = {
        'frequency': os.path.join(SCRIPTS_DIR, 'fetch_frequency.py'),
        'clustering': os.path.join(SCRIPTS_DIR, 'run_clustering.py'),
        'mapping': os.path.join(SCRIPTS_DIR, 'run_mapping.py'),
        'competitor_analysis': os.path.join(SCRIPTS_DIR, 'run_competitor_analysis.py'),
        'fetch_queries': os.path.join(SCRIPTS_DIR, 'fetch_yandex_queries.py'),
    }

    script_path = script_map.get(task_type)
    if not script_path:
        print(f"Unknown task type: {task_type}")
        return

    domain = payload.get('domain', '')
    args = [PYTHON_PATH, script_path]

    if task_type == 'frequency':
        args.extend([
            domain,
            str(user_id),
            payload.get('device', ''),
            payload.get('region', ''),
            payload.get('mode', 'all'),
            str(payload.get('minFrequency', 10)),
            str(task_id),
            str(payload.get('clusterId', 0)),
        ])
    elif task_type == 'clustering':
        args.extend([domain, str(user_id), str(task_id)])
    elif task_type == 'mapping':
        args.extend([domain, str(user_id), str(task_id)])
    elif task_type == 'competitor_analysis':
        cluster_id = payload.get('cluster_id', payload.get('clusterId', ''))
        args.extend([domain, str(cluster_id), str(user_id), str(task_id)])
    elif task_type == 'fetch_queries':
        args.extend([domain, str(user_id)])

    try:
        subprocess.Popen(args, cwd=project_root)
    except Exception as e:
        print(f"Failed to spawn task {task_id}: {e}")


def main() -> None:
    print(f"SEO Worker started (PID: {os.getpid()})")
    while True:
        try:
            tasks = get_pending_tasks()
            for task in tasks:
                _mark_scheduled(task['id'])
                run_task(task)
            time.sleep(2)
        except Exception as e:
            print(f"Worker loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
