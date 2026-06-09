import paramiko
import sys

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect('95.181.213.46', username='barnick', password='337733!@Az', timeout=10)
        
        # Get Nginx configuration
        cmd = "ls -la /etc/nginx/sites-enabled/"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdin.write("337733!@Az\n")
        stdin.flush()
        
        out = stdout.read().decode('utf-8', errors='replace').strip()
        err = stderr.read().decode('utf-8', errors='replace').strip()
        print("--- STDOUT ---")
        print(out)
        print("--- STDERR ---")
        print(err)
        
    except Exception as e:
        print("Error:", e)
    finally:
        ssh.close()

if __name__ == '__main__':
    main()
