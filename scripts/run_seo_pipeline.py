import json
import sys

from utils.bootstrap import bootstrap

bootstrap()

from config import Config
from scripts.check_positions import check_positions_task
from scripts.collect_cluster_keywords import collect_cluster_keywords_task
from scripts.fetch_frequency import fetch_frequency_task
from scripts.generate_structure import generate_structure_task
from scripts.run_competitor_analysis import run_competitor_analysis_task
from services.task_manager import TaskManager
from utils.retry import RetryExhausted, with_retry


def run_seo_pipeline_task(
    domain: str,
    user_id: int,
    cluster_id: int,
    task_id: int,
    target_url: str,
    region: str = "213",
    head_query: str | None = None,
) -> dict:
    tm = TaskManager(task_id)
    tm.set_status("running")

    def update_stage(progress: int, stage_num: int, stage_text: str):
        print(f"[{task_id}] Stage {stage_num}/8: {stage_text}")
        tm.update_progress(
            progress,
            {
                "stage": stage_num,
                "total_stages": 8,
                "stage_text": stage_text,
            },
        )

    def run_step(
        step_num: int,
        progress: int,
        name: str,
        func,
        *args,
        max_retries: int = 2,
        error_fatal: bool = False,
    ):
        try:
            retry_decorator = with_retry(
                max_retries=max_retries,
                base_delay=1.0,
                backoff_factor=3.0,
                on_retry=lambda e, a: print(f"[{task_id}] Step {step_num} retry {a}: {e}"),
            )
            update_stage(progress, step_num, name)
            result = retry_decorator(func)(*args)
            return result
        except RetryExhausted as e:
            if error_fatal:
                raise  # Will be caught by outer try/except
            print(f"WARN: Step {step_num} exhausted retries: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            if error_fatal:
                raise
            print(f"WARN: Step {step_num} error: {e}")
            return {"success": False, "error": str(e)}

    conn = None
    step_errors: dict[int, str] = {}
    try:
        domain = domain.lower().strip()
        if domain.startswith("http://"):
            domain = domain[7:]
        elif domain.startswith("https://"):
            domain = domain[8:]
        domain = domain.rstrip("/")

        # Check completed steps from payload
        try:
            conn_check = Config.get_conn()
            if Config.DB_TYPE == "postgresql":
                import psycopg2.extras
                cur_check = conn_check.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                import pymysql.cursors
                cur_check = conn_check.cursor(pymysql.cursors.DictCursor)
            cur_check.execute("SELECT payload FROM tasks WHERE id = %s", (task_id,))
            row = cur_check.fetchone()
            payload_data = json.loads(row["payload"]) if row and row["payload"] else {}
            conn_check.close()
        except Exception:
            payload_data = {}
        completed_steps: list[int] = payload_data.get("completed_steps", [])

        def mark_complete(step_num: int):
            completed_steps.append(step_num)
            tm.update_payload_partial({"completed_steps": completed_steps})

        # Step 1: Save target URL
        if 1 not in completed_steps:
            run_step(
                1,
                10,
                "Сохранение релевантного URL",
                _step_save_target,
                target_url,
                user_id,
                domain,
                cluster_id,
            )
            mark_complete(1)
        else:
            print(f"[{task_id}] Skipping step 1 (already completed)")

        # Step 2: Collect keywords (Wordstat - popular)
        if 2 not in completed_steps:
            run_step(
                2,
                20,
                "Сбор запросов из Яндекс Wordstat",
                collect_cluster_keywords_task,
                domain,
                user_id,
                cluster_id,
                head_query,
                "popular",
            )
            mark_complete(2)
        else:
            print(f"[{task_id}] Skipping step 2 (already completed)")

        # Step 3: Collect LSI (Wordstat - similar / right column)
        if 3 not in completed_steps:
            run_step(
                3,
                35,
                "Сбор LSI и похожих запросов (правая колонка)",
                collect_cluster_keywords_task,
                domain,
                user_id,
                cluster_id,
                head_query,
                "similar",
            )
            mark_complete(3)
        else:
            print(f"[{task_id}] Skipping step 3 (already completed)")

        # Step 4: Collect Frequency
        if 4 not in completed_steps:
            run_step(
                4,
                50,
                "Сбор частотности ключей кластера",
                fetch_frequency_task,
                domain,
                user_id,
                "",  # device
                region,
                "missing",  # mode
                10,  # min_freq
                task_id,
                cluster_id,
            )
            mark_complete(4)
        else:
            print(f"[{task_id}] Skipping step 4 (already completed)")

        # Step 5: Check Positions
        if 5 not in completed_steps:
            run_step(
                5,
                65,
                "Определение позиций в выдаче",
                check_positions_task,
                domain,
                cluster_id,
                user_id,
                region,
            )
            mark_complete(5)
        else:
            print(f"[{task_id}] Skipping step 5 (already completed)")

        # Step 6: Competitor Analysis
        if 6 not in completed_steps:
            run_step(
                6,
                80,
                "Анализ конкурентов в ТОП-10",
                run_competitor_analysis_task,
                domain,
                user_id,
                cluster_id,
                task_id,
            )
            mark_complete(6)
        else:
            print(f"[{task_id}] Skipping step 6 (already completed)")

        # Step 7: SEO Analysis (Step 6 saves analysis_data, this is a logic placeholder)
        if 7 not in completed_steps:
            update_stage(90, 7, "Генерация SEO-анализа текста (шаг 6 сохранил данные)")
            mark_complete(7)
        else:
            print(f"[{task_id}] Skipping step 7 (already completed)")

        # Step 8: Generate Structure
        if 8 not in completed_steps:
            keywords = []
            try:
                conn = Config.get_conn()
                if Config.DB_TYPE == "postgresql":
                    import psycopg2.extras
                    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                else:
                    import pymysql.cursors
                    cur = conn.cursor(pymysql.cursors.DictCursor)
                cur.execute(
                    "SELECT query FROM yandex_queries WHERE user_id = %s AND site_url = %s AND clustered = %s AND minus_word = 0",
                    (user_id, domain, cluster_id),
                )
                keywords = [r["query"] for r in cur.fetchall()]
                conn.close()
                conn = None
            except Exception as e:
                print(f"Error fetching keywords for step 8: {e}")

            res8 = run_step(
                8,
                95,
                "Формирование структуры статьи",
                generate_structure_task,
                domain,
                user_id,
                cluster_id,
                keywords,
            )
            if res8 and res8.get("success") and res8.get("structure"):
                try:
                    conn = Config.get_conn()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE cluster_analysis SET ideal_structure = %s WHERE user_id = %s AND site_url = %s AND cluster_id = %s",
                        (
                            json.dumps(res8["structure"], ensure_ascii=False),
                            user_id,
                            domain,
                            str(cluster_id),
                        ),
                    )
                    conn.commit()
                    conn.close()
                    conn = None
                except Exception as e:
                    print(f"Error saving ideal structure: {e}")
            mark_complete(8)
        else:
            print(f"[{task_id}] Skipping step 8 (already completed)")

        all_steps = {1, 2, 3, 4, 5, 6, 7, 8}
        success = all(s in completed_steps for s in all_steps)
        if success:
            update_stage(100, 8, "Анализ успешно завершен!")
            tm.set_status("completed")
            return {"success": True, "cluster_id": cluster_id}
        else:
            missed = [s for s in sorted(all_steps) if s not in completed_steps]
            tm.set_status("failed", f"Steps failed: {missed}")
            return {"success": False, "error": f"Steps not completed: {missed}"}

    except Exception as e:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        tm.set_status("failed", str(e))
        return {"success": False, "error": str(e)}


def _step_save_target(target_url: str, user_id: int, domain: str, cluster_id: int) -> dict:
    if not target_url:
        return {"success": True, "skipped": True}
    conn = Config.get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE target_url = VALUES(target_url)
        """,
        (user_id, domain, str(cluster_id), target_url),
    )
    conn.commit()
    conn.close()
    return {"success": True}


def main():
    if len(sys.argv) < 5:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "Usage: run_seo_pipeline.py <domain> <user_id> <cluster_id> <task_id> [target_url] [region] [head_query]",
                }
            )
        )
        sys.exit(1)

    domain = sys.argv[1]
    user_id = int(sys.argv[2])
    cluster_id = int(sys.argv[3])
    task_id = int(sys.argv[4])
    target_url = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "None" else ""
    region = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] != "None" else "213"
    head_query = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] != "None" else None

    result = run_seo_pipeline_task(
        domain, user_id, cluster_id, task_id, target_url, region, head_query
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
