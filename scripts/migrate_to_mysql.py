# scripts/migrate_to_mysql.py
import sys
import os
import json
import pymysql

# Get project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import Config

def migrate():
    print("Starting MySQL migration...")
    
    try:
        # Connect to MySQL (without DB first to create it)
        conn = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASS,
            charset='utf8mb4',
            autocommit=True
        )
        cur = conn.cursor()
        
        # Create DB if not exists
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE `{Config.MYSQL_DB}`")
        
        print(f"Database `{Config.MYSQL_DB}` ready")
        
        # 1. Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                password VARCHAR(255) NOT NULL,
                tokens INT DEFAULT 10000,
                balance DECIMAL(10,2) DEFAULT 0.00,
                yandex_token TEXT,
                is_blocked TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        """)
        
        # Ensure balance column exists (in case table already exists)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN balance DECIMAL(10,2) DEFAULT 0.00 AFTER tokens")
        except: pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN yandex_token TEXT AFTER balance")
        except: pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN is_blocked TINYINT(1) DEFAULT 0 AFTER yandex_token")
        except: pass
        
        # 2. Sites table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                domain VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)

        # 3. Settings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                `key` VARCHAR(255) UNIQUE NOT NULL,
                `value` VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB
        """)

        # Default settings
        defaults = {
            'clustering_rate': '0.10',
            'frequency_rate': '0.20',
            'position_new_rate': '0.25',
            'position_step_rate': '0.05'
        }
        for key, val in defaults.items():
            cur.execute("INSERT IGNORE INTO settings (`key`, `value`) VALUES (%s, %s)", (key, val))
        
        # 3. Yandex Queries table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS yandex_queries (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                query VARCHAR(500) NOT NULL,
                period_from VARCHAR(50),
                period_to VARCHAR(50),
                hits INT DEFAULT 0,
                hits_ym INT DEFAULT 0,
                hits_google INT DEFAULT 0,
                clicks INT DEFAULT 0,
                ctr DOUBLE DEFAULT 0,
                avg_position DOUBLE DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_check TIMESTAMP NULL,
                minus_word TINYINT DEFAULT 0,
                clustered INT DEFAULT 0,
                frequency INT DEFAULT 0,
                INDEX idx_user_site (user_id, site_url),
                INDEX idx_query (query),
                UNIQUE KEY user_site_query (user_id, site_url, query(255)),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 4. Cluster Mappings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cluster_mappings (
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                cluster_id INT NOT NULL,
                target_url TEXT,
                PRIMARY KEY (user_id, site_url, cluster_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 5. Cluster Analysis
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cluster_analysis (
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                cluster_id INT NOT NULL,
                analysis_data LONGTEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                raw_html LONGTEXT,
                PRIMARY KEY (user_id, site_url, cluster_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 6. Wordstat Settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wordstat_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(255) NOT NULL,
                device VARCHAR(100),
                region VARCHAR(100),
                region_name VARCHAR(255),
                is_default TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 7. Cluster LSI
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cluster_lsi (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                cluster_id INT NOT NULL,
                keyword VARCHAR(500) NOT NULL,
                frequency INT DEFAULT 0,
                UNIQUE KEY user_site_cluster_kw (user_id, site_url, cluster_id, keyword(255)),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 8. Cluster Names
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cluster_names (
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                cluster_id INT NOT NULL,
                cluster_name VARCHAR(500) NOT NULL,
                is_favorite TINYINT DEFAULT 0,
                is_pinned TINYINT DEFAULT 0,
                pinned_order INT DEFAULT 0,
                PRIMARY KEY (user_id, site_url, cluster_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 9. SERP Cache (Shared)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS serp_cache (
                cache_key VARCHAR(255) PRIMARY KEY,
                urls LONGTEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        """)
        
        # 10. Tasks Table for Worker
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                task_type VARCHAR(100) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                payload JSON,
                result JSON,
                progress INT DEFAULT 0,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                started_at DATETIME,
                finished_at DATETIME,
                INDEX idx_status (status),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 11. Page Content
        cur.execute("""
            CREATE TABLE IF NOT EXISTS page_content (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                page_url VARCHAR(500) NOT NULL,
                full_html LONGTEXT,
                editable_html LONGTEXT,
                non_editable_html LONGTEXT,
                last_fetched TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY user_page (user_id, page_url(255)),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)
        
        # 12. Page Versions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS page_versions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                page_url VARCHAR(500) NOT NULL,
                editable_html LONGTEXT,
                keywords JSON,
                miratext_task_id VARCHAR(255),
                llm_model_used VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)

        # 14. Query History (Position tracking)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                query VARCHAR(500) NOT NULL,
                position INT,
                found_url TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_query_date (user_id, site_url, query(255), checked_at),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)

        # 15. Payment History
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payment_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'RUB',
                status VARCHAR(50) DEFAULT 'pending',
                order_id VARCHAR(100) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)

        # 14. Billing History
        cur.execute("""
            CREATE TABLE IF NOT EXISTS billing_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                description VARCHAR(500),
                type ENUM('deposit', 'charge') NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB
        """)

        print("All tables created successfully")
        
        conn.close()
        print("Migration complete!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
