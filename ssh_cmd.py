import paramiko
import sys

HOST = '95.181.213.46'
USER = 'barnick'
PASSWORD = '337733!@Az'

def main():
    if len(sys.argv) < 2:
        print("Usage: python ssh_cmd.py 'command'")
        return

    cmd = sys.argv[1]
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)

    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', 'replace')
    err = stderr.read().decode('utf-8', 'replace')
    
    if out: print("STDOUT:\n" + out)
    if err: print("STDERR:\n" + err)

    ssh.close()

if __name__ == '__main__':
    main()
