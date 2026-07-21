import os
import sys

import paramiko
from dotenv import load_dotenv

load_dotenv()

SSH_HOST = os.getenv("SSH_HOST")
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")

if not all([SSH_HOST, SSH_USER, SSH_PASSWORD]):
    sys.exit("Error: SSH_HOST, SSH_USER and SSH_PASSWORD must be set in .env")

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SSH_HOST, username=SSH_USER, password=SSH_PASSWORD)
    
    node_script = """
const db = require('./nodejs-app/db');
(async () => {
    try {
        const [rows] = await db.query('SELECT username, balance FROM users WHERE username = ?', ['ekaterinatourkrd']);
        console.log(JSON.stringify(rows[0]));
    } catch (e) {
        console.error(e);
    } finally {
        process.exit(0);
    }
})();
"""
    
    import base64
    b64_script = base64.b64encode(node_script.encode()).decode()
    cmd_write = f"cd ~/seo-auto-cluster && echo {b64_script} | base64 -d > check_balance.js && node check_balance.js && rm check_balance.js"
    
    stdin, stdout, stderr = client.exec_command(cmd_write)
    
    out = stdout.read().decode('utf-8', errors='ignore')
    
    print("STDOUT:", out.encode('ascii', errors='ignore').decode())
        
finally:
    client.close()
