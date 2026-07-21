import paramiko
import os
import stat
import sys

# Connect
host = '95.181.213.46'
user = 'barnick'
password = '337733!@Az'

local_dir = r"c:\Users\BarNick\Desktop\seo-auto-cluster"
remote_dir = "/home/barnick/seo-auto-cluster"

ignore_dirs = {'.venv', 'node_modules', '__pycache__', '.git', '.ruff_cache', '.tmp', 'scratch', 'data', 'results'}
ignore_files = {'yandex_geo.csv', 'seo_data.db', 'nul'}

def sync_dir(sftp, remote_path, local_path):
    print(f"Checking {remote_path}...")
    if not os.path.exists(local_path):
        os.makedirs(local_path)
    
    try:
        remote_files = sftp.listdir_attr(remote_path)
    except Exception as e:
        print(f"Error accessing {remote_path}: {e}")
        return

    for attr in remote_files:
        filename = attr.filename
        if filename in ignore_dirs or filename in ignore_files:
            continue
            
        rpath = remote_path + '/' + filename
        lpath = os.path.join(local_path, filename)
        
        if stat.S_ISDIR(attr.st_mode):
            sync_dir(sftp, rpath, lpath)
        else:
            download = False
            if not os.path.exists(lpath):
                download = True
                print(f"New file found: {rpath}")
            else:
                lstat = os.stat(lpath)
                if attr.st_size != lstat.st_size or abs(attr.st_mtime - lstat.st_mtime) > 2: # 2 seconds tolerance
                    download = True
                    print(f"File modified: {rpath} (remote: {attr.st_size}b, local: {lstat.st_size}b)")
                    
            if download:
                print(f"Downloading {rpath} to {lpath}...")
                sftp.get(rpath, lpath)
                # optionally set mtime?
                # os.utime(lpath, (attr.st_atime, attr.st_mtime))
                print("Downloaded.")

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting...")
    ssh.connect(host, username=user, password=password, timeout=10)
    sftp = ssh.open_sftp()
    
    print("Syncing...")
    sync_dir(sftp, remote_dir, local_dir)
    
    sftp.close()
    ssh.close()
    print("Done.")

if __name__ == '__main__':
    main()
