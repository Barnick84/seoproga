# scripts/update_minus.py
import sys
import os
import json

# Fix console encoding on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, project_root)

from config import Config

def update_minus_words(user_id, domain, keywords):
    if not user_id or not domain or not keywords:
        return {"success": False, "error": "Missing parameters", "updated": 0}

    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        updated = 0
        # Debug log
        sys.stderr.write(f"DEBUG: Updating {len(keywords)} keywords for {domain} (user {user_id})\n")
        
        for kw in keywords:
            cur.execute(
                "UPDATE yandex_queries SET minus_word = 1 WHERE user_id = %s AND site_url = %s AND query = %s",
                (user_id, domain, kw),
            )
            count = cur.rowcount
            updated += count
            if count == 0:
                 sys.stderr.write(f"DEBUG: No match for kw='{kw}' domain='{domain}' user={user_id}\n")

        conn.commit()
        if updated == 0 and len(keywords) > 0:
            return {"success": False, "error": "Ни один запрос не найден в базе для этих параметров", "updated": 0}
        return {"success": True, "updated": updated}
    except Exception as e:
        sys.stderr.write(f"ERROR in update_minus_words: {str(e)}\n")
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

if __name__ == "__main__":
    # Check if we have arguments or if we should read from stdin
    if len(sys.argv) >= 3:
        user_id = sys.argv[1]
        domain = sys.argv[2]
        keywords = sys.argv[3:]
    else:
        # Try reading from stdin
        try:
            # Force UTF-8 decoding for stdin buffer on Windows
            input_data = sys.stdin.buffer.read().decode('utf-8', errors='replace')
            if input_data:
                data = json.loads(input_data)
                user_id = data.get("user_id")
                domain = data.get("domain")
                keywords = data.get("keywords", [])
                # Log for debugging
                # print(f"DEBUG: Received {len(keywords)} keywords for {domain}", file=sys.stderr)
            else:
                print(json.dumps({"success": False, "error": "No data provided via args or stdin"}))
                sys.exit(1)
        except Exception as e:
            print(json.dumps({"success": False, "error": f"Failed to parse stdin: {str(e)}"}))
            sys.exit(1)
    
    if not user_id or not domain:
        print(json.dumps({"success": False, "error": "user_id and domain are required"}))
        sys.exit(1)
        
    result = update_minus_words(user_id, domain, keywords)
    print(json.dumps(result, ensure_ascii=False))
