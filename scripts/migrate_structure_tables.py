# scripts/migrate_structure_tables.py
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.bootstrap import bootstrap
bootstrap()

from config import Config

def migrate():
    print(f"Running migration for DB_TYPE={Config.DB_TYPE}...")

    if Config.DB_TYPE == "postgresql":
        import psycopg2
        conn = psycopg2.connect(Config.get_pg_dsn())
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_structure (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                structure_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT idx_user_site UNIQUE (user_id, site_url)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS page_types (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                icon VARCHAR(50) DEFAULT 'fa-file',
                color VARCHAR(20) DEFAULT '#3b82f6',
                template_description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        conn.close()
    else:
        conn = Config.get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_structure (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                structure_json LONGTEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY idx_user_site (user_id, site_url)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS page_types (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                icon VARCHAR(50) DEFAULT 'fa-file',
                color VARCHAR(20) DEFAULT '#3b82f6',
                template_description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
        conn.commit()
        conn.close()
    
    print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
