const mysql = require('mysql2/promise');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

async function migrate() {
    const connection = await mysql.createConnection({
        host: process.env.MYSQL_HOST || 'localhost',
        user: process.env.MYSQL_USER || 'root',
        password: process.env.MYSQL_PASSWORD || 'root',
        database: process.env.MYSQL_DBNAME || 'seo_auto'
    });

    console.log('Migrating database...');
    
    try {
        await connection.query('ALTER TABLE cluster_names ADD COLUMN is_favorite TINYINT DEFAULT 0');
        console.log('Added is_favorite column');
    } catch (e) {
        console.log('is_favorite column already exists or error:', e.message);
    }

    try {
        await connection.query('ALTER TABLE cluster_names ADD COLUMN is_pinned TINYINT DEFAULT 0');
        console.log('Added is_pinned column');
    } catch (e) {
        console.log('is_pinned column already exists or error:', e.message);
    }

    try {
        await connection.query('ALTER TABLE cluster_names ADD COLUMN pinned_order INTEGER DEFAULT 0');
        console.log('Added pinned_order column');
    } catch (e) {
        console.log('pinned_order column already exists or error:', e.message);
    }

    await connection.end();
    console.log('Migration finished.');
}

migrate();
