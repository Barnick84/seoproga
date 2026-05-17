const db = require('../db.js');

async function run() {
    try {
        const [tables] = await db.query('SHOW TABLES');
        for (let t of tables) {
            let tname = Object.values(t)[0];
            const [schema] = await db.query(`SHOW CREATE TABLE \`${tname}\``);
            console.log(schema[0]['Create Table']);
            console.log('---');
        }
    } catch (e) {
        console.error(e);
    } finally {
        process.exit(0);
    }
}
run();
