import paramiko
import sys

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect('95.181.213.46', username='barnick', password='337733!@Az', timeout=10)
        
        # SQL query to get tasks for user 4
        cmd = """mysql -u seoapp -pseoapp123 seo_app -e "SELECT id, task_type, status, progress, error, created_at, started_at, finished_at FROM tasks WHERE user_id = 4 ORDER BY created_at DESC LIMIT 20;" """
        print("--- TASKS ---")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        print(stdout.read().decode('utf-8', errors='replace').strip())

    except Exception as e:
        print("Error:", e)
    finally:
        ssh.close()

if __name__ == '__main__':
    main()
