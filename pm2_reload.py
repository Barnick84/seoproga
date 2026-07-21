"""check_502.py — Fetches remote logs and checks process status."""
import paramiko

HOST = '95.181.213.46'
USER = 'barnick'
PASSWORD = '337733!@Az'

def run(ssh, cmd):
    _, out, err = ssh.exec_command(cmd)
    o = out.read().decode('utf-8', 'replace').strip()
    e = err.read().decode('utf-8', 'replace').strip()
    return o, e

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    print("=== Port 3000 Status ===")
    o1, _ = run(ssh, "ss -tlnp | grep :3000 || echo 'DOWN'")
    print(o1)

    print("\n=== Node Process ===")
    o2, _ = run(ssh, "pgrep -a node || echo 'no node'")
    print(o2)

    print("\n=== Last 50 lines of server.log ===")
    o3, _ = run(ssh, "tail -50 /home/barnick/seo-auto-cluster/nodejs-app/server.log")
    if o3:
        # replace unprintable/emoji
        print(o3.encode('ascii', 'ignore').decode('ascii'))
    
    print("\n=== NGINX Error Log ===")
    o4, _ = run(ssh, "sudo -n tail -20 /var/log/nginx/error.log 2>/dev/null || echo 'no sudo/access'")
    print(o4)

    ssh.close()

if __name__ == '__main__':
    main()
