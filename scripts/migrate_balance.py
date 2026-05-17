# scripts/migrate_balance.py
import sys
import os
import pymysql

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from config import Config

def migrate_balance():
    print("Updating balances for existing users...")
    
    try:
        conn = Config.get_mysql_conn()
        cur = conn.cursor()
        
        # Add 10000 to balance for all users who have 0.00
        cur.execute("UPDATE users SET balance = balance + 10000 WHERE balance = 0.00")
        affected = cur.rowcount
        
        # Also add a billing history entry for these users
        cur.execute("SELECT id FROM users WHERE balance >= 10000")
        users = cur.fetchall()
        for user in users:
            user_id = user['id']
            # Check if already has a deposit entry
            cur.execute("SELECT id FROM billing_history WHERE user_id = %s AND type = 'deposit' AND description = 'Initial bonus'", (user_id,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO billing_history (user_id, amount, description, type) VALUES (%s, %s, %s, %s)",
                    (user_id, 10000, "Initial bonus", "deposit")
                )
        
        conn.commit()
        print(f"Success! Updated balances for {affected} users.")
        conn.close()
        
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    migrate_balance()
