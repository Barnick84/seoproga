const db = require('./db.js');

async function migrate() {
    try {
        console.log('Creating cluster_seo_history table...');
        await db.query(`
            CREATE TABLE IF NOT EXISTS cluster_seo_history (
                user_id INT NOT NULL,
                site_url VARCHAR(255) NOT NULL,
                cluster_id INT NOT NULL,
                analysis_date DATE NOT NULL,
                intent_type VARCHAR(50) DEFAULT NULL,
                seo_plan_content LONGTEXT,
                optimized_html LONGTEXT,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, site_url, cluster_id, analysis_date),
                CONSTRAINT cluster_seo_history_ibfk_1 FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
        `);
        console.log('Migration completed successfully.');
    } catch (e) {
        console.error('Migration failed:', e);
    } finally {
        process.exit(0);
    }
}

migrate();
