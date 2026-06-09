import paramiko
import sys

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('95.181.213.46', username='barnick', password='337733!@Az')
    
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
