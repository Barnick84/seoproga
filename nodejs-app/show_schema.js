const mysql = require('mysql2/promise');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

async function showSchema() {
    const connection = await mysql.createConnection({
        host: process.env.MYSQL_HOST || 'localhost',
        user: process.env.MYSQL_USER || 'root',
        password: process.env.MYSQL_PASSWORD || 'root',
        database: process.env.MYSQL_DBNAME || 'seo_auto'
    });

    try {
        const [rows] = await connection.query('SHOW CREATE TABLE cluster_names');
        console.log(rows[0]['Create Table']);
    } catch (e) {
        console.log('Error:', e.message);
    }
    await connection.end();
}

showSchema();
