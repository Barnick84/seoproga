# scripts/user_auth.py
import sys
import os
import json
import uuid
import hashlib
from datetime import datetime

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

def hash_password(password, salt=None):
    if not salt:
        salt = uuid.uuid4().hex
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return salt + h.hex()

def register(username, password, email=None, yandex_token=None):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        # Check if username exists
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return {"success": False, "error": "Пользователь с таким логином уже существует"}

        # Check if email exists
        if email:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                return {"success": False, "error": "Пользователь с таким Email уже существует"}

        # Create user with 10000 tokens
        password_hash = hash_password(password)
        cur.execute(
            "INSERT INTO users (username, password, email, tokens, yandex_token) VALUES (%s, %s, %s, %s, %s)",
            (username, password_hash, email, 10000, yandex_token),
        )
        user_id = cur.lastrowid
        return {"success": True, "user_id": user_id, "tokens": 10000}
    finally:
        conn.close()

def login(username, password):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT id, password, tokens FROM users WHERE username = %s", (username,)
        )
        row = cur.fetchone()

        if not row:
            return {"success": False, "error": "Неверный логин или пароль"}

        user_id, stored_password, tokens = row['id'], row['password'], row['tokens']

        # Verify password
        salt = stored_password[:32]
        expected = hash_password(password, salt)

        if expected != stored_password:
            return {"success": False, "error": "Неверный логин или пароль"}

        return {"success": True, "user_id": user_id, "tokens": tokens}
    finally:
        conn.close()

def get_user(user_id):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, username, tokens FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row['id'], "username": row['username'], "tokens": row['tokens']}
    finally:
        conn.close()

def check_site_owner(site_domain):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()

    try:
        cur.execute("SELECT user_id FROM sites WHERE domain = %s", (site_domain,))
        row = cur.fetchone()
        if row and row['user_id']:
            return row['user_id']
    except:
        pass
    finally:
        conn.close()

def get_settings(user_id):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT yandex_token FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return {"yandex_token": row['yandex_token'] if row and row['yandex_token'] else ""}
    finally:
        conn.close()

def update_settings(user_id, yandex_token):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE users SET yandex_token = %s WHERE id = %s", (yandex_token, user_id))
        return {"success": True}
    finally:
        conn.close()

def change_password(user_id, current_password, new_password):
    conn = Config.get_mysql_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Пользователь не найден"}
            
        stored_password = row['password']
        salt = stored_password[:32]
        expected = hash_password(current_password, salt)
        
        if expected != stored_password:
            return {"success": False, "error": "Неверный текущий пароль"}
            
        new_hash = hash_password(new_password)
        cur.execute("UPDATE users SET password = %s WHERE id = %s", (new_hash, user_id))
        return {"success": True}
    finally:
        conn.close()

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""

    if action == "register":
        username = sys.argv[2] if len(sys.argv) > 2 else ""
        password = sys.argv[3] if len(sys.argv) > 3 else ""
        email = sys.argv[4] if len(sys.argv) > 4 else ""
        yandex_token = sys.argv[5] if len(sys.argv) > 5 else ""
        result = register(username, password, email, yandex_token)
        print(json.dumps(result, ensure_ascii=False))
    elif action == "login":
        username = sys.argv[2] if len(sys.argv) > 2 else ""
        password = sys.argv[3] if len(sys.argv) > 3 else ""
        result = login(username, password)
        print(json.dumps(result, ensure_ascii=False))
    elif action == "check_owner":
        domain = sys.argv[2] if len(sys.argv) > 2 else ""
        owner = check_site_owner(domain)
        print(json.dumps({"owner": owner}, ensure_ascii=False))
    elif action == "get_settings":
        user_id = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(get_settings(user_id), ensure_ascii=False))
    elif action == "update_settings":
        user_id = sys.argv[2] if len(sys.argv) > 2 else ""
        token = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(update_settings(user_id, token), ensure_ascii=False))
    elif action == "change_password":
        user_id = sys.argv[2] if len(sys.argv) > 2 else ""
        curr = sys.argv[3] if len(sys.argv) > 3 else ""
        new = sys.argv[4] if len(sys.argv) > 4 else ""
        print(json.dumps(change_password(user_id, curr, new), ensure_ascii=False))
