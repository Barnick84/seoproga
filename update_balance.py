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
        const [result] = await db.query('UPDATE users SET balance = 1000 WHERE username = ?', ['ekaterinatourkrd']);
        console.log("Update result:", result.affectedRows > 0 ? "Success" : "User not found");
        
        const [rows] = await db.query('SELECT username, balance FROM users WHERE username = ?', ['ekaterinatourkrd']);
        console.log("Current user:", rows[0]);
    } catch (e) {
        console.error(e);
    } finally {
        process.exit(0);
    }
})();
"""
    
    import base64
    b64_script = base64.b64encode(node_script.encode()).decode()
    cmd = f"cd ~/seo-auto-cluster && node -e \"Buffer.from('{b64_script}', 'base64').toString('utf8').split('\\n').forEach(l => eval(l));\""
    # Actually eval() line by line is bad for async/await syntax.
    # Better to write to file and run it.
    
    cmd_write = f"cd ~/seo-auto-cluster && echo {b64_script} | base64 -d > update_balance.js && node update_balance.js && rm update_balance.js"
    
    stdin, stdout, stderr = client.exec_command(cmd_write)
    
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    
    print("STDOUT:", out)
    if err:
        print("STDERR:", err)
        
finally:
    client.close()
