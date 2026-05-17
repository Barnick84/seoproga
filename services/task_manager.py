# services/task_manager.py
import json
from datetime import datetime
from config import Config

class TaskManager:
    def __init__(self, task_id: int):
        self.task_id = task_id

    def update_progress(self, progress: int, result: dict = None):
        if not self.task_id:
            return
            
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        try:
            if result:
                cur.execute(
                    "UPDATE tasks SET progress = %s, result = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (progress, json.dumps(result), self.task_id)
                )
            else:
                cur.execute(
                    "UPDATE tasks SET progress = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (progress, self.task_id)
                )
        finally:
            conn.close()

    def set_status(self, status: str, error: str = None):
        if not self.task_id:
            return
            
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        try:
            now = datetime.now()
            if status == 'running':
                cur.execute(
                    "UPDATE tasks SET status = %s, started_at = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, now, self.task_id)
                )
            elif status in ['completed', 'failed']:
                cur.execute(
                    "UPDATE tasks SET status = %s, finished_at = %s, error = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, now, error, self.task_id)
                )
            else:
                cur.execute(
                    "UPDATE tasks SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, self.task_id)
                )
        finally:
            conn.close()
