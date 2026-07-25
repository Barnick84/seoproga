# services/task_manager.py
import json
from datetime import datetime

from config import Config


class TaskManager:
    def __init__(self, task_id: int):
        self.task_id = task_id
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            self._conn = Config.get_conn()
        return self._conn

    def close(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def update_progress(self, progress: int, result: dict = None) -> None:
        if not self.task_id:
            return
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            if result:
                cur.execute(
                    "UPDATE tasks SET progress = %s, result = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (progress, json.dumps(result), self.task_id),
                )
            else:
                cur.execute(
                    "UPDATE tasks SET progress = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (progress, self.task_id),
                )
            conn.commit()
        except Exception as e:
            print(f"TaskManager.update_progress error: {e}")
            self.close()

    def update_payload_partial(self, updates: dict) -> None:
        if not self.task_id:
            return
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT payload FROM tasks WHERE id = %s", (self.task_id,))
            row = cur.fetchone()
            if row:
                payload = json.loads(row["payload"]) if row["payload"] else {}
            else:
                payload = {}
            payload.update(updates)
            cur.execute(
                "UPDATE tasks SET payload = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (json.dumps(payload), self.task_id),
            )
            conn.commit()
        except Exception as e:
            print(f"TaskManager.update_payload_partial error: {e}")
            self.close()

    def set_status(self, status: str, error: str = None) -> None:
        if not self.task_id:
            return
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            now = datetime.now()
            if status == "running":
                cur.execute(
                    "UPDATE tasks SET status = %s, started_at = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, now, self.task_id),
                )
            elif status in ["completed", "failed"]:
                cur.execute(
                    "UPDATE tasks SET status = %s, finished_at = %s, error = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, now, error, self.task_id),
                )
            else:
                cur.execute(
                    "UPDATE tasks SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, self.task_id),
                )
            conn.commit()
        except Exception as e:
            print(f"TaskManager.set_status error: {e}")
            self.close()
        finally:
            if status in ("completed", "failed"):
                self.close()
