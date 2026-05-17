# services/worker.py
import sys
import os
import time
import json
import subprocess
from datetime import datetime

# Fix console encoding on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config

PYTHON_PATH = sys.executable

def get_pending_tasks():
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT 5")
        return cur.fetchall()
    finally:
        conn.close()

def run_task(task):
    task_id = task['id']
    user_id = task['user_id']
    task_type = task['task_type']
    payload = json.loads(task['payload']) if isinstance(task['payload'], str) else task['payload']

    print(f"[{datetime.now()}] Starting task {task_id} ({task_type}) for user {user_id}")

    script_map = {
        'frequency': 'nodejs-app/scripts/fetch_frequency.py',
        'clustering': 'nodejs-app/scripts/run_clustering.py',
        'mapping': 'nodejs-app/scripts/run_mapping.py',
        'competitor_analysis': 'nodejs-app/scripts/run_competitor_analysis.py',
        'fetch_queries': 'nodejs-app/scripts/fetch_yandex_queries.py'
    }

    script_path = script_map.get(task_type)
    if not script_path:
        print(f"Unknown task type: {task_type}")
        return

    # Prepare arguments based on task type
    args = [PYTHON_PATH, script_path]
    
    if task_type == 'frequency':
        args.extend([
            payload.get('domain'),
            str(user_id),
            payload.get('device', ''),
            payload.get('region', ''),
            payload.get('mode', 'all'),
            str(payload.get('minFrequency', 10)),
            str(task_id),
            str(payload.get('clusterId', 0))
        ])
    elif task_type == 'fetch_queries':
        args.extend([payload.get('domain'), str(user_id)])
    # Add other task types as they are refactored...

    try:
        # Run as a separate process
        process = subprocess.Popen(args, cwd=project_root)
        # We don't wait here if we want parallel execution, but for now let's just let it run.
        # The script itself will update the status in DB.
    except Exception as e:
        print(f"Failed to spawn task {task_id}: {e}")

def main():
    print(f"SEO Worker started (PID: {os.getpid()})")
    while True:
        try:
            tasks = get_pending_tasks()
            for task in tasks:
                # Mark as 'scheduled' to avoid multiple workers picking it up
                conn = Config.get_mysql_conn()
                cur = conn.cursor()
                cur.execute("UPDATE tasks SET status = 'scheduled' WHERE id = %s", (task['id'],))
                conn.close()
                
                run_task(task)
            
            time.sleep(2) # Poll every 2 seconds
        except Exception as e:
            print(f"Worker loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
