from unittest.mock import MagicMock, patch

from services.worker import fetch_and_schedule_tasks, run_task


def test_fetch_and_schedule_tasks_success():
    with patch("services.worker.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate successful fetch
        mock_cur.fetchall.return_value = [{"id": 1, "status": "pending"}]
        mock_cur.rowcount = 1

        tasks = fetch_and_schedule_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == 1
        mock_cur.execute.assert_any_call(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED",
            (5,),
        )
        mock_cur.execute.assert_any_call(
            "UPDATE tasks SET status = 'scheduled' WHERE id = %s AND status = 'pending'",
            (1,),
        )
        mock_conn.commit.assert_called_once()


def test_fetch_and_schedule_tasks_race_condition():
    with patch("services.worker.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate fetch success but update failure (race condition)
        mock_cur.fetchall.return_value = [{"id": 1, "status": "pending"}]
        mock_cur.rowcount = 0

        tasks = fetch_and_schedule_tasks(1)
        assert len(tasks) == 0
        mock_conn.commit.assert_called_once()


@patch("services.worker.subprocess.Popen")
def test_run_task_unknown_type(mock_popen):
    with patch("services.worker.Config.get_conn") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        task = {"id": 42, "user_id": 1, "task_type": "unknown_task_type", "payload": "{}"}

        run_task(task)

        # Should not call subprocess
        mock_popen.assert_not_called()

        # Should mark task as failed
        assert mock_cur.execute.called
        assert mock_conn.commit.called
