import paramiko
import time

HOST = '95.181.213.46'
USER = 'barnick'
PASSWORD = '337733!@Az'

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    print("Killing existing Node.js server...")
    ssh.exec_command("pkill -9 -f 'server.js'")
    time.sleep(2)

    print("Starting Node.js server...")
    cmd = "cd /home/barnick/seo-auto-cluster/nodejs-app && nohup node server.js </dev/null >server.log 2>&1 & sleep 2"
    ssh.exec_command(cmd)
    
    time.sleep(2)
    _, stdout, _ = ssh.exec_command("pgrep -a node")
    processes = stdout.read().decode().strip()
    print("Running node processes:")
    print(processes)

    ssh.close()

if __name__ == '__main__':
    main()
