import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
import json

def cleanup():
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    
    # 1. Find duplicates for kislovodsk.openvisa.online
    cur.execute("SELECT id, user_id FROM sites WHERE domain = 'kislovodsk.openvisa.online' ORDER BY id")
    rows = cur.fetchall()
    
    if len(rows) > 1:
        print(f"Found {len(rows)} entries for kislovodsk.openvisa.online")
        # Keep the first one, delete others
        to_delete = [r['id'] for r in rows[1:]]
        for site_id in to_delete:
            print(f"Deleting site ID {site_id}")
            cur.execute("DELETE FROM sites WHERE id = %s", (site_id,))
        conn.commit()
    else:
        print("No duplicates found for kislovodsk.openvisa.online")
        
    conn.close()

if __name__ == "__main__":
    cleanup()
