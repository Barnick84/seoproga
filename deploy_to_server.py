"""
deploy_to_server.py — загружает изменённые файлы на сервер и перезапускает pm2.
Обратный по логике к sync_from_server.py (LOCAL → REMOTE).
"""
import paramiko
import os
import stat
import sys

HOST = '95.181.213.46'
USER = 'barnick'
PASSWORD = '337733!@Az'

LOCAL_DIR = r"c:\Users\BarNick\Desktop\seo-auto-cluster"
REMOTE_DIR = "/home/barnick/seo-auto-cluster"

IGNORE_DIRS = {'.venv', 'node_modules', '__pycache__', '.git', '.ruff_cache',
               '.tmp', 'scratch', 'data', 'results', 'miratext_img', 'html_temp',
               'yandex_seo_pipeline'}
IGNORE_FILES = {'yandex_geo.csv', 'seo_data.db', 'nul', 'list', 'plugin', 'query',
                'deploy_to_server.py', 'sync_from_server.py',
                'text-analysis-2026-05-07_22-36.xlsx',
                'output_article.html', 'server.log'}

uploaded = 0
skipped = 0


def remote_exists(sftp, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except FileNotFoundError:
        return False


def ensure_remote_dir(sftp, remote_path: str) -> None:
    parts = remote_path.replace('\\', '/').split('/')
    current = ''
    for part in parts:
        if not part:
            current += '/'
            continue
        current = current.rstrip('/') + '/' + part
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def upload_dir(sftp, local_path: str, remote_path: str) -> None:
    global uploaded, skipped

    local_entries = os.listdir(local_path)

    for name in local_entries:
        if name in IGNORE_DIRS or name in IGNORE_FILES:
            continue

        lpath = os.path.join(local_path, name)
        rpath = remote_path + '/' + name

        if os.path.isdir(lpath):
            if not remote_exists(sftp, rpath):
                sftp.mkdir(rpath)
                print(f"  [MKDIR] {rpath}")
            upload_dir(sftp, lpath, rpath)
        elif os.path.isfile(lpath):
            do_upload = False

            try:
                rstat = sftp.stat(rpath)
                lstat = os.stat(lpath)
                if lstat.st_size != rstat.st_size or abs(lstat.st_mtime - rstat.st_mtime) > 2:
                    do_upload = True
            except FileNotFoundError:
                do_upload = True

            if do_upload:
                print(f"  [UPLOAD] {rpath}")
                sftp.put(lpath, rpath)
                uploaded += 1
            else:
                skipped += 1


def run_remote(ssh: paramiko.SSHClient, cmd: str) -> str:
    print(f"\n  $ {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out:
        print(f"    {out}")
    if err:
        print(f"    STDERR: {err}")
    return out


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print(f"Connecting to {HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    sftp = ssh.open_sftp()

    print(f"\nUploading LOCAL → REMOTE")
    print(f"  {LOCAL_DIR}")
    print(f"  → {REMOTE_DIR}\n")

    upload_dir(sftp, LOCAL_DIR, REMOTE_DIR)
    sftp.close()

    print(f"\nUpload complete: {uploaded} files uploaded, {skipped} skipped (unchanged).")

    print("\n--- Post-deploy steps ---")

    # Install dotenv if not present
    run_remote(ssh, "cd ~/seo-auto-cluster/nodejs-app && npm list dotenv --depth=0 2>/dev/null || npm install dotenv --save")

    # Reload Node.js app
    run_remote(ssh, "pm2 reload all --update-env 2>&1 || pm2 start ~/seo-auto-cluster/nodejs-app/server.js --name seo-node -- --update-env")

    # Restart worker if running
    run_remote(ssh, "pm2 describe worker 2>/dev/null | grep -q 'online' && pm2 restart worker || echo 'worker not in pm2, skipping'")

    # Show pm2 status
    run_remote(ssh, "pm2 list")

    ssh.close()
    print("\nDeploy complete!")


if __name__ == '__main__':
    main()
