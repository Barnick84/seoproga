const express = require('express');
const cors = require('cors');
const { spawn } = require('child_process');
const path = require('path');
const crypto = require('crypto');
const db = require('./db');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Path to virtual environment python
const PYTHON_PATH = process.platform === 'win32'
    ? path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', '.venv', 'bin', 'python');

// Session storage: session_id -> { user_id, username }
const sessions = {};

// Admin Password from user request
const ADMIN_PASSWORD = '12131415!@Az';
const adminErrors = [];

// Catch console.error to admin log
const originalConsoleError = console.error;
console.error = (...args) => {
    adminErrors.unshift({
        time: new Date().toLocaleString(),
        message: args.map(a => typeof a === 'object' ? JSON.stringify(a) : a).join(' ')
    });
    if (adminErrors.length > 100) adminErrors.pop();
    originalConsoleError.apply(console, args);
};

// Middleware: Admin Auth
const authenticateAdmin = (req, res, next) => {
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader === `Bearer ${ADMIN_PASSWORD}`) {
        next();
    } else {
        res.status(401).json({ error: 'Unauthorized admin access' });
    }
};

// Helper: Get system settings
async function getSystemSettings() {
    try {
        const [rows] = await db.query('SELECT `key`, `value` FROM settings');
        const settings = {};
        rows.forEach(r => settings[r.key] = r.value);
        return {
            clustering_rate: parseFloat(settings.clustering_rate || 0.10),
            frequency_rate: parseFloat(settings.frequency_rate || 0.20),
            position_new_rate: parseFloat(settings.position_new_rate || 0.25),
            position_step_rate: parseFloat(settings.position_step_rate || 0.05)
        };
    } catch (e) {
        return { clustering_rate: 0.10, frequency_rate: 0.20, position_new_rate: 0.25, position_step_rate: 0.05 };
    }
}

// Helper: Check and deduct balance
async function checkAndDeductBalance(userId, amount, description) {
    const [rows] = await db.query('SELECT balance FROM users WHERE id = ?', [userId]);
    if (rows.length === 0) throw new Error('User not found');
    
    const balance = parseFloat(rows[0].balance);
    if (balance < amount) {
        throw new Error(`Недостаточно средств. Требуется: ${amount.toFixed(2)} ₽, доступно: ${balance.toFixed(2)} ₽`);
    }

    const conn = await db.getConnection();
    try {
        await conn.beginTransaction();
        await conn.query('UPDATE users SET balance = balance - ? WHERE id = ?', [amount, userId]);
        await conn.query(
            'INSERT INTO billing_history (user_id, amount, description, type) VALUES (?, ?, ?, ?)',
            [userId, amount, description, 'charge']
        );
        await conn.commit();
    } catch (err) {
        await conn.rollback();
        throw err;
    } finally {
        conn.release();
    }
}

// API: Admin Login
app.post('/api/admin/login', (req, res) => {
    const { password } = req.body;
    if (password === ADMIN_PASSWORD) {
        res.json({ success: true, token: ADMIN_PASSWORD });
    } else {
        res.status(401).json({ success: false, error: 'Неверный пароль администратора' });
    }
});

// API: Admin - Get Tariffs
app.get('/api/admin/tariffs', authenticateAdmin, async (req, res) => {
    const settings = await getSystemSettings();
    res.json({
        clustering: settings.clustering_rate,
        frequency: settings.frequency_rate,
        position_new: settings.position_new_rate,
        position_step: settings.position_step_rate
    });
});

// API: Admin - Update Tariffs
app.post('/api/admin/tariffs/update', authenticateAdmin, async (req, res) => {
    try {
        const { clustering, frequency, position_new, position_step } = req.body;
        const conn = await db.getConnection();
        try {
            await conn.beginTransaction();
            const updates = {
                'clustering_rate': clustering,
                'frequency_rate': frequency,
                'position_new_rate': position_new,
                'position_step_rate': position_step
            };
            for (const [key, val] of Object.entries(updates)) {
                if (val !== undefined) {
                    await conn.query('UPDATE settings SET `value` = ? WHERE `key` = ?', [val.toString(), key]);
                }
            }
            await conn.commit();
            res.json({ success: true });
        } catch (err) {
            await conn.rollback();
            throw err;
        } finally {
            conn.release();
        }
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// API: Admin - Get Users
app.get('/api/admin/users', authenticateAdmin, async (req, res) => {
    try {
        const [users] = await db.query('SELECT id, email, balance, yandex_token, is_blocked, created_at FROM users ORDER BY id DESC');
        res.json({ users });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// API: Admin - Get Sites
app.get('/api/admin/sites', authenticateAdmin, async (req, res) => {
    try {
        const [sites] = await db.query(`
            SELECT s.user_id, s.domain, 
            (SELECT COUNT(*) FROM yandex_queries y WHERE y.user_id = s.user_id AND y.site_url = s.domain) as query_count
            FROM sites s
        `);
        res.json({ sites });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// API: Admin - Get Payments
app.get('/api/admin/payments', authenticateAdmin, async (req, res) => {
    try {
        const [payments] = await db.query(`
            SELECT b.*, u.email 
            FROM billing_history b 
            JOIN users u ON b.user_id = u.id 
            ORDER BY b.created_at DESC LIMIT 200
        `);
        res.json({ payments });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// API: Admin - Get Logs
app.get('/api/admin/logs', authenticateAdmin, (req, res) => {
    res.json({ logs: adminErrors });
});

// API: Admin - Update User (Balance, Token, Block)
app.post('/api/admin/users/update', authenticateAdmin, async (req, res) => {
    try {
        const { userId, balance, yandex_token, is_blocked } = req.body;
        if (!userId) return res.status(400).json({ error: 'userId required' });

        const [oldUser] = await db.query('SELECT balance FROM users WHERE id = ?', [userId]);
        if (oldUser.length === 0) return res.status(404).json({ error: 'User not found' });

        const conn = await db.getConnection();
        try {
            await conn.beginTransaction();
            
            // If balance changed, log it
            if (balance !== undefined) {
                const diff = parseFloat(balance) - parseFloat(oldUser[0].balance);
                if (Math.abs(diff) > 0.001) {
                    await conn.query(
                        'INSERT INTO billing_history (user_id, amount, description, type) VALUES (?, ?, ?, ?)',
                        [userId, Math.abs(diff), `Админ-корректировка баланса (было: ${oldUser[0].balance})`, diff > 0 ? 'deposit' : 'charge']
                    );
                }
            }

            const updates = [];
            const params = [];
            if (balance !== undefined) { updates.push('balance = ?'); params.push(balance); }
            if (yandex_token !== undefined) { updates.push('yandex_token = ?'); params.push(yandex_token); }
            if (is_blocked !== undefined) { 
                updates.push('is_blocked = ?'); 
                params.push(is_blocked ? 1 : 0);
                // Clear session if blocked
                if (is_blocked) {
                    for (const sid in sessions) {
                        if (sessions[sid].user_id == userId) delete sessions[sid];
                    }
                }
            }

            if (updates.length > 0) {
                params.push(userId);
                await conn.query(`UPDATE users SET ${updates.join(', ')} WHERE id = ?`, params);
            }

            await conn.commit();
            res.json({ success: true });
        } catch (err) {
            await conn.rollback();
            throw err;
        } finally {
            conn.release();
        }
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Middleware: Authenticate user
const authenticate = async (req, res, next) => {
    const sessionId = req.headers['authorization'];
    if (!sessionId || !sessions[sessionId]) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    
    // Check if blocked in DB
    try {
        const [rows] = await db.query('SELECT is_blocked FROM users WHERE id = ?', [sessions[sessionId].user_id]);
        if (rows.length > 0 && rows[0].is_blocked) {
            delete sessions[sessionId];
            return res.status(403).json({ error: 'Account blocked' });
        }
    } catch (e) {}

    req.user = sessions[sessionId];
    next();
};

// Helper: normalize URL
function normalizeUrl(url) {
    url = url.toLowerCase().trim();
    if (url.startsWith('http://')) url = url.slice(7);
    else if (url.startsWith('https://')) url = url.slice(8);
    else if (url.startsWith('http:')) url = url.slice(5);
    else if (url.startsWith('https:')) url = url.slice(6);
    return url.replace(/\/$/, '');
}

// Helper: call Python script
function callPython(scriptPath, args = [], input = null) {
    return new Promise((resolve, reject) => {
        const py = spawn(PYTHON_PATH, [scriptPath, ...args], {
            cwd: path.resolve(__dirname, '..'),
            stdio: ['pipe', 'pipe', 'pipe'],
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, // Force UTF-8 environment
            shell: false
        });
        
        if (input) {
            py.stdin.write(input);
            py.stdin.end();
        }
        
        let stdoutChunks = [];
        let stderrChunks = [];
        
        py.stdout.on('data', (chunk) => { stdoutChunks.push(chunk); });
        py.stderr.on('data', (chunk) => { stderrChunks.push(chunk); });
        
        py.on('close', (code) => {
            const stdout = Buffer.concat(stdoutChunks).toString('utf-8');
            const stderr = Buffer.concat(stderrChunks).toString('utf-8');
            
            if (code !== 0) {
                reject(new Error(stderr || `Process exited with code ${code}`));
            } else {
                resolve(stdout);
            }
        });
        
        py.on('error', reject);
    });
}

// API: User registration
app.post('/api/auth/register', async (req, res) => {
    try {
        const { username, password, email, yandex_token } = req.body;
        if (!username || !password) {
            return res.status(400).json({ error: 'Username and password required' });
        }
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'user_auth.py'),
            ['register', username, password, email || '', yandex_token || '']
        );
        
        const data = JSON.parse(result);
        if (data.success) {
            const sessionId = require('crypto').randomBytes(32).toString('hex');
            sessions[sessionId] = { user_id: data.user_id, username: username };
            res.json({ success: true, session: sessionId, user_id: data.user_id });
        } else {
            res.json(data);
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: User login
app.post('/api/auth/login', async (req, res) => {
    try {
        const { username, password } = req.body;
        if (!username || !password) {
            return res.status(400).json({ error: 'Username and password required' });
        }
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'user_auth.py'),
            ['login', username, password]
        );
        
        const data = JSON.parse(result);
        if (data.success) {
            const sessionId = require('crypto').randomBytes(32).toString('hex');
            sessions[sessionId] = { user_id: data.user_id, username: username };
            res.json({ success: true, session: sessionId, tokens: data.tokens, user_id: data.user_id });
        } else {
            res.json(data);
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Check session
app.get('/api/auth/session', authenticate, (req, res) => {
    res.json({ authenticated: true, username: req.user.username, user_id: req.user.user_id });
});

// API: User logout
app.post('/api/auth/logout', (req, res) => {
    const session = req.headers.authorization;
    if (session && sessions[session]) {
        delete sessions[session];
    }
    res.json({ success: true });
});

// --- MONETIZATION API ---

// API: Get user info (balance, etc)
app.get('/api/user-info', authenticate, async (req, res) => {
    try {
        const [rows] = await db.query('SELECT username, balance FROM users WHERE id = ?', [req.user.user_id]);
        if (rows.length === 0) return res.status(404).json({ error: 'User not found' });
        res.json({ success: true, user: rows[0] });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Create Payment (Tegro Money)
app.post('/api/create-payment', authenticate, async (req, res) => {
    try {
        const { amount } = req.body;
        const minAmount = 500;
        if (!amount || amount < minAmount) {
            return res.status(400).json({ error: `Минимальная сумма пополнения ${minAmount} руб.` });
        }

        const shop_id = process.env.TEGRO_SHOP_ID || 'D0F98E7D7742609DC508D86BB7500914';
        const secret = process.env.TEGRO_SECRET_KEY || '';
        const order_id = `ORDER_${Date.now()}_${req.user.user_id}`;
        const currency = 'RUB';

        // 1. Log pending payment
        await db.query(
            'INSERT INTO payment_history (user_id, amount, currency, order_id, status) VALUES (?, ?, ?, ?, ?)',
            [req.user.user_id, amount, currency, order_id, 'pending']
        );

        // 2. Prepare signature
        const data = {
            shop_id: shop_id,
            amount: amount,
            currency: currency,
            order_id: order_id
        };
        
        const sortedKeys = Object.keys(data).sort();
        const str = sortedKeys.map(k => `${k}=${data[k]}`).join('&');
        const sign = crypto.createHash('md5').update(str + secret).digest('hex');

        // 3. Construct Tegro URL
        const tegroUrl = `https://tegro.money/pay/?shop_id=${shop_id}&amount=${amount}&currency=${currency}&order_id=${order_id}&sign=${sign}`;
        
        res.json({ success: true, payment_url: tegroUrl });
    } catch (error) {
        console.error('Payment creation error:', error);
        res.status(500).json({ error: error.message });
    }
});

// API: Payment Callback (Webhook from Tegro)
app.post('/api/payment-callback', express.urlencoded({ extended: true }), async (req, res) => {
    try {
        const { shop_id, amount, order_id, sign } = req.body;
        const secret = process.env.TEGRO_SECRET_KEY || '';

        if (!shop_id || !amount || !order_id || !sign) {
            return res.status(400).send('Missing params');
        }

        const data = { ...req.body };
        delete data.sign;
        const sortedKeys = Object.keys(data).sort();
        const str = sortedKeys.map(k => `${k}=${data[k]}`).join('&');
        const expectedSign = crypto.createHash('md5').update(str + secret).digest('hex');

        if (sign !== expectedSign) {
            console.error('Invalid Tegro sign');
            return res.status(400).send('Invalid sign');
        }

        const [payments] = await db.query('SELECT * FROM payment_history WHERE order_id = ? AND status = ?', [order_id, 'pending']);
        if (payments.length === 0) {
            return res.status(200).send('Already processed or not found');
        }

        const payment = payments[0];
        
        const conn = await db.getConnection();
        try {
            await conn.beginTransaction();
            await conn.query('UPDATE users SET balance = balance + ? WHERE id = ?', [amount, payment.user_id]);
            await conn.query('UPDATE payment_history SET status = ? WHERE id = ?', ['success', payment.id]);
            await conn.query(
                'INSERT INTO billing_history (user_id, amount, description, type) VALUES (?, ?, ?, ?)',
                [payment.user_id, amount, `Пополнение баланса (Заказ ${order_id})`, 'deposit']
            );
            await conn.commit();
            res.send('OK');
        } catch (err) {
            await conn.rollback();
            throw err;
        } finally {
            conn.release();
        }
    } catch (error) {
        console.error('Tegro Callback error:', error);
        res.status(500).send('Internal Server Error');
    }
});

// API: Get Billing History
app.get('/api/billing-history', authenticate, async (req, res) => {
    try {
        const [billing] = await db.query(
            'SELECT * FROM billing_history WHERE user_id = ? ORDER BY created_at DESC',
            [req.user.user_id]
        );
        const [payments] = await db.query(
            'SELECT * FROM payment_history WHERE user_id = ? ORDER BY created_at DESC',
            [req.user.user_id]
        );
        res.json({ success: true, billing, payments });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get user settings and sites
app.get('/api/user/settings', authenticate, async (req, res) => {
    try {
        const settingsResult = await callPython(
            path.join(__dirname, 'scripts', 'user_auth.py'),
            ['get_settings', req.user.user_id]
        );
        
        const [sites] = await db.query(
            "SELECT domain FROM sites WHERE user_id = ?",
            [req.user.user_id]
        );
        
        const jsonMatch = settingsResult.match(/\{.*\}/s);
        const settings = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(settingsResult);
        
        res.json({ 
            success: true, 
            yandex_token: settings.yandex_token || '',
            sites: sites.map(s => s.domain)
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Update user settings
app.post('/api/user/settings', authenticate, async (req, res) => {
    try {
        const { yandex_token } = req.body;
        const result = await callPython(
            path.join(__dirname, 'scripts', 'user_auth.py'),
            ['update_settings', req.user.user_id, yandex_token || '']
        );
        const jsonMatch = result.match(/\{.*\}/s);
        const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Change password
app.post('/api/user/change-password', authenticate, async (req, res) => {
    try {
        const { current_password, new_password } = req.body;
        if (!current_password || !new_password) {
            return res.status(400).json({ error: 'Current and new passwords required' });
        }
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'user_auth.py'),
            ['change_password', req.user.user_id, current_password, new_password]
        );
        const jsonMatch = result.match(/\{.*\}/s);
        const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Add site
app.post('/api/sites', authenticate, async (req, res) => {
    try {
        const { domain } = req.body;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        
        // 1. Check if domain already owned by another user
        const checkOwner = await callPython(
            path.join(__dirname, 'scripts', 'user_auth.py'),
            ['check_owner', normalizedDomain]
        );
        
        try {
            const ownerData = JSON.parse(checkOwner);
            if (ownerData.owner && ownerData.owner !== req.user.user_id) {
                return res.status(400).json({ 
                    success: false,
                    message: 'Этот сайт уже привязан к другому пользователю' 
                });
            }
        } catch (e) {}

        // 2. Check if domain is linked to WM
        const checkResult = await callPython(
            path.join(__dirname, 'scripts', 'check_domain.py'),
            [normalizedDomain, req.user.user_id]
        );
        
        const checkData = JSON.parse(checkResult);
        if (!checkData.linked) {
            return res.status(400).json({ success: false, message: 'Домен не привязан к вашему аккаунту Яндекс.Вебмастера' });
        }
        
        // 3. Add to sites DB
        const result = await callPython(
            path.join(__dirname, 'scripts', 'add_site.py'),
            [normalizedDomain, req.user.user_id]
        );
        
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get all sites
app.get('/api/sites', authenticate, async (req, res) => {
    try {
        const result = await callPython(
            path.join(__dirname, 'scripts', 'get_sites.py'),
            [req.user.user_id]
        );
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get keywords from DB
app.get('/api/keywords', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        const args = [req.user.user_id];
        if (domain) args.push(normalizeUrl(domain));
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'get_keywords.py'),
            args
        );
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Check if domain is linked to WM
app.post('/api/check-domain', authenticate, async (req, res) => {
    try {
        const { domain } = req.body;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        const result = await callPython(
            path.join(__dirname, 'scripts', 'check_domain.py'),
            [normalizedDomain, req.user.user_id]
        );
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});



// API: Update minus words in DB
app.post('/api/minus-words', authenticate, async (req, res) => {
    try {
        const { domain, keywords } = req.body;
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'update_minus.py'),
            [],
            JSON.stringify({ user_id: req.user.user_id, domain: normalizeUrl(domain), keywords })
        );
        
        try {
            const data = JSON.parse(result);
            res.json(data);
        } catch {
            res.json({ success: false });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Clear minus words
app.post('/api/clear-minus', authenticate, async (req, res) => {
    try {
        const { domain } = req.body;
        if (!domain) {
            return res.status(400).json({ error: 'Domain required' });
        }
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'clear_minus.py'),
            [req.user.user_id, normalizeUrl(domain)]
        );
        
        try {
            const data = JSON.parse(result);
            res.json(data);
        } catch {
            res.json({ success: false });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Run clustering
app.post('/api/run-clustering', authenticate, async (req, res) => {
    try {
        const { domain } = req.body;
        if (!domain) {
            return res.status(400).json({ error: 'Domain required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        const settings = await getSystemSettings();

        // Calculate cost: clustering_rate RUB per keyword
        const [countRows] = await db.query(
            "SELECT COUNT(*) as count FROM yandex_queries WHERE user_id = ? AND site_url = ? AND minus_word = 0 AND clustered = 0",
            [req.user.user_id, normalizedDomain]
        );
        const kwCount = countRows[0].count;
        if (kwCount > 0) {
            const cost = kwCount * settings.clustering_rate;
            await checkAndDeductBalance(req.user.user_id, cost, `Кластеризация ${kwCount} запросов (${normalizedDomain})`);
        }

        const result = await callPython(
            path.join(__dirname, 'scripts', 'run_clustering.py'),
            [normalizedDomain, req.user.user_id]
        );
        
        try {
            // Extract JSON from output (might contain PROGRESS: logs)
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch (err) {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Run mapping (streaming progress)
app.get('/api/run-mapping-stream', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        
        res.setHeader('Content-Type', 'text/plain');
        res.setHeader('Transfer-Encoding', 'chunked');
        
        const py = require('child_process').spawn(PYTHON_PATH, [
            path.join(__dirname, 'scripts', 'run_mapping.py'),
            normalizedDomain,
            req.user.user_id
        ], {
            cwd: path.resolve(__dirname, '..')
        });
        
        py.stdout.on('data', (data) => {
            res.write(data);
        });
        
        py.stderr.on('data', (data) => {
            console.error(`Mapping error: ${data}`);
        });
        
        py.on('close', (code) => {
            res.end();
        });
    } catch (error) {
        res.status(500).write(JSON.stringify({ error: error.message }));
        res.end();
    }
});

// API: Run mapping
app.post('/api/run-mapping', authenticate, async (req, res) => {
    try {
        const { domain } = req.body;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'run_mapping.py'),
            [normalizeUrl(domain), req.user.user_id]
        );
        
        try {
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch (err) {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Track running analysis processes
const runningAnalyses = new Set();

// API: Check if analysis is running
app.get('/api/analysis-status', authenticate, (req, res) => {
    const { domain } = req.query;
    if (!domain) return res.status(400).json({ error: 'Domain required' });
    const normalizedDomain = normalizeUrl(domain);
    res.json({ running: runningAnalyses.has(`${req.user.user_id}:${normalizedDomain}`) });
});

// API: Run competitor analysis (Streaming)
app.get('/api/run-competitor-analysis-stream', authenticate, (req, res) => {
    const { domain } = req.query;
    if (!domain) return res.status(400).json({ error: 'Domain required' });

    const normalizedDomain = normalizeUrl(domain);
    const analysisKey = `${req.user.user_id}:${normalizedDomain}`;
    if (runningAnalyses.has(analysisKey)) {
        return res.status(409).json({ error: 'Analysis already running for this domain' });
    }

    runningAnalyses.add(analysisKey);

    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Transfer-Encoding', 'chunked');
    res.flushHeaders(); 

    const scriptPath = path.join(__dirname, 'scripts', 'run_competitor_analysis.py');
    const py = spawn(PYTHON_PATH, [scriptPath, normalizedDomain, req.user.user_id], {
        cwd: path.resolve(__dirname, '..'),
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' }
    });

    py.stdout.on('data', (data) => {
        res.write(data.toString());
    });

    py.stderr.on('data', (data) => {
        console.error(`Python stderr: ${data}`);
    });

    py.on('close', (code) => {
        runningAnalyses.delete(analysisKey);
        res.end();
    });
});

// API: Update target URL for cluster
app.post('/api/cluster/target-url', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, targetUrl } = req.body;
        if (!domain || !clusterId || !targetUrl) {
            return res.status(400).json({ error: 'Missing parameters' });
        }
        const normalizedDomain = normalizeUrl(domain);
        
        // Update the cluster_mappings table
        await db.query(
            "UPDATE cluster_mappings SET target_url = ? WHERE user_id = ? AND site_url = ? AND cluster_id = ?",
            [targetUrl, req.user.user_id, normalizedDomain, clusterId]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Check positions
app.get('/api/cluster/check-positions-stream', authenticate, async (req, res) => {
    const { domain, clusterId, region } = req.query;
    if (!domain || !clusterId) {
        return res.status(400).json({ error: 'Missing parameters' });
    }

    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const normalizedDomain = normalizeUrl(domain);
    const pythonScript = path.join(__dirname, 'scripts', 'check_positions.py');
    const child = spawn(PYTHON_PATH, [pythonScript, normalizedDomain, clusterId, req.user.user_id, region || '']);

    let output = '';

    child.stdout.on('data', (data) => {
        const lines = data.toString().split('\n');
        lines.forEach(line => {
            if (line.startsWith('PROGRESS:')) {
                res.write(`data: ${JSON.stringify({ type: 'progress', message: line.trim() })}\n\n`);
            } else if (line.trim()) {
                output += line;
            }
        });
    });

    child.stderr.on('data', (data) => {
        console.error(`stderr: ${data}`);
    });

    child.on('close', (code) => {
        try {
            const finalResult = JSON.parse(output);
            res.write(`data: ${JSON.stringify({ type: 'done', result: finalResult })}\n\n`);
        } catch (e) {
            res.write(`data: ${JSON.stringify({ type: 'error', message: output || 'Process failed' })}\n\n`);
        }
        res.end();
    });
});

app.post('/api/cluster/check-positions', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.body;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Missing parameters' });
        }
        const normalizedDomain = normalizeUrl(domain);
        
        // Call Python script to check positions
        const result = await callPython(
            path.join(__dirname, 'scripts', 'check_positions.py'),
            [normalizedDomain, clusterId, req.user.user_id]
        );
        
        try {
            res.json(JSON.parse(result));
        } catch {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Remove LSI keyword and move to minus words
app.post('/api/cluster/remove-lsi', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, keyword } = req.body;
        if (!domain || !clusterId || !keyword) {
            return res.status(400).json({ error: 'Missing parameters' });
        }
        const normalizedDomain = normalizeUrl(domain);
        
        // 1. Delete from cluster_lsi
        await db.query(
            "DELETE FROM cluster_lsi WHERE user_id = ? AND site_url = ? AND cluster_id = ? AND keyword = ?",
            [req.user.user_id, normalizedDomain, clusterId, keyword]
        );
        
        // 2. Add to yandex_queries as minus_word (upsert)
        const [rows] = await db.query(
            "SELECT id FROM yandex_queries WHERE user_id = ? AND site_url = ? AND query = ?",
            [req.user.user_id, normalizedDomain, keyword]
        );
        
        if (rows.length > 0) {
            await db.query(
                "UPDATE yandex_queries SET minus_word = 1 WHERE id = ?",
                [rows[0].id]
            );
        } else {
            await db.query(
                "INSERT INTO yandex_queries (user_id, site_url, query, minus_word, hits) VALUES (?, ?, ?, 1, 0)",
                [req.user.user_id, normalizedDomain, keyword]
            );
        }
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Run SEO analysis (new)
app.post('/api/cluster/run-seo-analysis', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.body;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Missing parameters' });
        }
        const normalizedDomain = normalizeUrl(domain);
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'run_seo_analysis.py'),
            [normalizedDomain, clusterId, req.user.user_id]
        );
        
        try {
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Run competitor analysis (Legacy/Sync)
app.post('/api/run-competitor-analysis', authenticate, async (req, res) => {
    try {
        const { domain } = req.body;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'run_competitor_analysis.py'),
            [normalizeUrl(domain), req.user.user_id]
        );
        
        try {
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get analysis results
app.get('/api/analysis', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        const [rows] = await db.query(
            "SELECT cluster_id, analysis_data FROM cluster_analysis WHERE user_id = ? AND site_url = ?",
            [req.user.user_id, normalizedDomain]
        );
        
        const analysis = {};
        rows.forEach(row => {
            try {
                analysis[row.cluster_id] = JSON.parse(row.analysis_data);
            } catch (e) {
                analysis[row.cluster_id] = null;
            }
        });
        res.json({ analysis });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get mappings
app.get('/api/mappings', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        const [rows] = await db.query(
            "SELECT cluster_id, target_url FROM cluster_mappings WHERE user_id = ? AND site_url = ?",
            [req.user.user_id, normalizedDomain]
        );
        
        const mappings = {};
        rows.forEach(row => {
            mappings[row.cluster_id] = row.target_url;
        });
        res.json({ mappings });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Move keywords between clusters
app.post('/api/move-keywords', authenticate, async (req, res) => {
    try {
        const { domain, keywords, target } = req.body;
        if (!domain || !keywords || !target) {
            return res.status(400).json({ error: 'Domain, keywords and target required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        const targetCluster = target === 'unclustered' ? 0 : parseInt(target);
        
        if (targetCluster === 0) {
            await db.query(
                "UPDATE yandex_queries SET clustered = 0 WHERE user_id = ? AND site_url = ? AND query IN (?)",
                [req.user.user_id, normalizedDomain, keywords]
            );
        } else {
            await db.query(
                "UPDATE yandex_queries SET clustered = ? WHERE user_id = ? AND site_url = ? AND query IN (?)",
                [targetCluster, req.user.user_id, normalizedDomain, keywords]
            );
        }
        res.json({ success: true, moved: keywords.length });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Delete cluster
app.post('/api/delete-cluster', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.body;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Domain and clusterId required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        
        const [result] = await db.query(
            "UPDATE yandex_queries SET clustered = 0 WHERE user_id = ? AND site_url = ? AND clustered = ?",
            [req.user.user_id, normalizedDomain, clusterId]
        );
        
        res.json({ success: true, moved: result.affectedRows });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Run mapping for single cluster
app.get('/api/run-mapping-single', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.query;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Domain and clusterId required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        const result = await callPython(
            path.join(__dirname, 'scripts', 'run_mapping.py'),
            [normalizedDomain, req.user.user_id, clusterId]
        );
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Save manual mapping
app.post('/api/save-mapping-manual', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, url } = req.body;
        if (!domain || !clusterId || !url) {
            return res.status(400).json({ error: 'Domain, clusterId and url required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        await db.query(
            "INSERT INTO cluster_mappings (user_id, site_url, cluster_id, target_url) VALUES (?, ?, ?, ?) ON DUPLICATE KEY UPDATE target_url = VALUES(target_url)",
            [req.user.user_id, normalizedDomain, clusterId, url]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Run competitor analysis for single cluster
app.get('/api/run-competitor-analysis-single', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.query;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Domain and clusterId required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        const result = await callPython(
            path.join(__dirname, 'scripts', 'run_competitor_analysis.py'),
            [normalizedDomain, req.user.user_id, clusterId]
        );
        try {
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Prepare SEO brief using AI
app.get('/api/prepare-seo-brief', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.query;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Domain and clusterId required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        const result = await callPython(
            path.join(__dirname, 'scripts', 'prepare_seo_brief.py'),
            [normalizedDomain, clusterId, req.user.user_id]
        );
        try {
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch {
            res.json({ success: false, error: result });
        }
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Test SEO 2026 Pipeline
app.get('/api/test-seo-2026', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.query;
        if (!domain || !clusterId) return res.status(400).json({ error: 'Domain and clusterId required' });

        const normalizedDomain = normalizeUrl(domain);

        // 1. Get Keywords
        const [queries] = await db.query(
            "SELECT query FROM yandex_queries WHERE user_id = ? AND site_url = ? AND clustered = ?",
            [req.user.user_id, normalizedDomain, clusterId]
        );
        if (queries.length === 0) return res.status(404).json({ error: 'No keywords found in cluster' });
        const clusterKeywords = queries.map(q => q.query).join(', ');

        // 2. Get Target URL
        const [mappings] = await db.query(
            "SELECT target_url FROM cluster_mappings WHERE user_id = ? AND site_url = ? AND cluster_id = ?",
            [req.user.user_id, normalizedDomain, clusterId]
        );
        const targetUrl = mappings.length > 0 ? mappings[0].target_url : `https://${normalizedDomain}/`;

        // 3. Call Python Pipeline (SEO 2026)
        const pipelinePath = path.join(__dirname, '..', 'yandex_seo_pipeline', 'main.py');
        const configPath = path.join(__dirname, '..', 'yandex_seo_pipeline', 'config.yaml');
        
        // We use spawn because it's more flexible for long running
        const result = await callPython(pipelinePath, [
            '--url', targetUrl,
            '--cluster', clusterKeywords,
            '--config', configPath
        ]);

        // Note: yandex_seo_pipeline/main.py currently prints success and logs to stdout. 
        // For production, it should return JSON. I'll mock a JSON response for the frontend if needed, 
        // or ensure the script returns JSON.
        
        // For now, I'll read the output file if it exists, or parse stdout if I modify the script.
        // Let's modify yandex_seo_pipeline/main.py to return JSON when called with a flag or by default.
        
        // Actually, let's just parse the stdout or read the generated file.
        const fs = require('fs');
        const outputPath = path.join(__dirname, '..', 'output_article.html');
        let html = '';
        if (fs.existsSync(outputPath)) {
            html = fs.readFileSync(outputPath, 'utf8');
        }

        res.json({ 
            success: true, 
            logs: result.split('\n').filter(l => l.trim()), 
            optimized_html: html 
        });

    } catch (error) {
        console.error('SEO 2026 Test Error:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Fetch queries from Yandex Webmaster
app.get('/api/fetch-wm-queries', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        if (!domain) return res.status(400).json({ error: 'Domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        const result = await callPython(
            path.join(__dirname, 'scripts', 'fetch_yandex_queries.py'),
            [normalizedDomain, req.user.user_id]
        );
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Fetch available hosts from Yandex Webmaster
app.get('/api/get-wm-hosts', authenticate, async (req, res) => {
    try {
        const result = await callPython(
            path.join(__dirname, 'scripts', 'get_yandex_hosts.py'),
            [req.user.user_id]
        );
        res.json(JSON.parse(result));
    } catch (error) {
        res.status(500).json({ success: false, error: error.message });
    }
});

// API: Disband cluster
app.post('/api/disband-cluster', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.body;
        if (!domain || !clusterId) {
            return res.status(400).json({ error: 'Domain and clusterId required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        await db.query(
            "UPDATE yandex_queries SET clustered = 0 WHERE user_id = ? AND site_url = ? AND clustered = ?",
            [req.user.user_id, normalizedDomain, clusterId]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Update cluster name
app.post('/api/update-cluster-name', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, name } = req.body;
        if (!domain || !clusterId || name === undefined) {
            return res.status(400).json({ error: 'Domain, clusterId and name required' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        await db.query(
            "INSERT INTO cluster_names (user_id, site_url, cluster_id, cluster_name) VALUES (?, ?, ?, ?) ON DUPLICATE KEY UPDATE cluster_name = VALUES(cluster_name)",
            [req.user.user_id, normalizedDomain, clusterId, name]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Toggle cluster favorite
app.post('/api/toggle-cluster-favorite', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, isFavorite } = req.body;
        const normalizedDomain = normalizeUrl(domain);
        await db.query(
            "INSERT INTO cluster_names (user_id, site_url, cluster_id, cluster_name, is_favorite) VALUES (?, ?, ?, '', ?) ON DUPLICATE KEY UPDATE is_favorite = VALUES(is_favorite)",
            [req.user.user_id, normalizedDomain, clusterId, isFavorite ? 1 : 0]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Toggle cluster pinned
app.post('/api/toggle-cluster-pinned', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, isPinned } = req.body;
        const normalizedDomain = normalizeUrl(domain);
        await db.query(
            "INSERT INTO cluster_names (user_id, site_url, cluster_id, cluster_name, is_pinned) VALUES (?, ?, ?, '', ?) ON DUPLICATE KEY UPDATE is_pinned = VALUES(is_pinned)",
            [req.user.user_id, normalizedDomain, clusterId, isPinned ? 1 : 0]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Update pinned order
app.post('/api/update-pinned-order', authenticate, async (req, res) => {
    try {
        const { domain, orders } = req.body; // orders: { clusterId: order }
        const normalizedDomain = normalizeUrl(domain);
        const conn = await db.getConnection();
        try {
            await conn.beginTransaction();
            for (const [id, order] of Object.entries(orders)) {
                await conn.query(
                    "INSERT INTO cluster_names (user_id, site_url, cluster_id, cluster_name, pinned_order) VALUES (?, ?, ?, '', ?) ON DUPLICATE KEY UPDATE pinned_order = VALUES(pinned_order)",
                    [req.user.user_id, normalizedDomain, id, order]
                );
            }
            await conn.commit();
            res.json({ success: true });
        } catch (e) {
            await conn.rollback();
            throw e;
        } finally {
            conn.release();
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get Wordstat settings
app.get('/api/wordstat-settings', authenticate, async (req, res) => {
    try {
        const [rows] = await db.query(
            "SELECT id, name, device, region, region_name, is_default FROM wordstat_settings WHERE user_id = ? ORDER BY is_default DESC, id ASC",
            [req.user.user_id]
        );
        res.json({ settings: rows });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Save Wordstat setting
app.post('/api/wordstat-settings', authenticate, async (req, res) => {
    try {
        const { name, device, region, region_name } = req.body;
        if (!name || !device) return res.status(400).json({ error: 'name and device required' });
        
        const [result] = await db.query(
            "INSERT INTO wordstat_settings (user_id, name, device, region, region_name, is_default) VALUES (?, ?, ?, ?, ?, 0)",
            [req.user.user_id, name, device, region || '', region_name || 'Все регионы']
        );
        res.json({ success: true, id: result.insertId });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Delete Wordstat setting
app.delete('/api/wordstat-settings/:id', authenticate, async (req, res) => {
    try {
        const { id } = req.params;
        await db.query(
            "DELETE FROM wordstat_settings WHERE id = ? AND user_id = ? AND is_default = 0",
            [id, req.user.user_id]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get geo regions from CSV
app.get('/api/geo-regions', (req, res) => {
    const fs = require('fs');
    const csvPath = path.join(__dirname, '..', 'yandex_geo.csv');
    if (!fs.existsSync(csvPath)) {
        return res.json({ regions: [] });
    }
    try {
        const content = fs.readFileSync(csvPath, 'utf8');
        const lines = content.trim().split('\n');
        const regions = [];
        for (let i = 1; i < lines.length; i++) {
            const line = lines[i].replace(/\r/g, '');
            const parts = line.match(/"([^"]*)"/g);
            if (parts && parts.length >= 3) {
                const id = parts[0].replace(/"/g, '');
                const place = parts[1].replace(/"/g, '');
                const parent = parts[2].replace(/"/g, '');
                regions.push({ id, place, parent });
            }
        }
        res.json({ regions });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// API: Get LSI keywords for cluster
app.get('/api/cluster-lsi', authenticate, async (req, res) => {
    try {
        const { domain, clusterId } = req.query;
        if (!domain || !clusterId) return res.status(400).json({ error: 'domain and clusterId required' });
        
        const normalizedDomain = normalizeUrl(domain);
        const [rows] = await db.query(
            "SELECT keyword, frequency FROM cluster_lsi WHERE user_id = ? AND site_url = ? AND cluster_id = ? ORDER BY frequency DESC",
            [req.user.user_id, normalizedDomain, clusterId]
        );
        res.json({ lsi: rows });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get cluster names (after frequency update)
app.get('/api/cluster-names', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        if (!domain) return res.status(400).json({ error: 'domain required' });
        
        const normalizedDomain = normalizeUrl(domain);
        const [rows] = await db.query(
            "SELECT cluster_id, cluster_name, is_favorite, is_pinned, pinned_order FROM cluster_names WHERE user_id = ? AND site_url = ?",
            [req.user.user_id, normalizedDomain]
        );
        
        const metadata = {};
        rows.forEach(row => {
            metadata[row.cluster_id] = {
                name: row.cluster_name,
                is_favorite: !!row.is_favorite,
                is_pinned: !!row.is_pinned,
                pinned_order: row.pinned_order || 0
            };
        });
        res.json({ metadata });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Check frequency job status (Now checks tasks table)
app.get('/api/frequency-status', authenticate, async (req, res) => {
    try {
        const { domain } = req.query;
        if (!domain) return res.status(400).json({ error: 'domain required' });
        
        const [rows] = await db.execute(
            "SELECT id, status, progress FROM tasks WHERE user_id = ? AND task_type = 'frequency' AND status IN ('pending', 'scheduled', 'running') ORDER BY created_at DESC LIMIT 1",
            [req.user.user_id]
        );
        
        if (rows.length > 0) {
            res.json({ running: true, task: rows[0] });
        } else {
            res.json({ running: false });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Run frequency collection (Queue-based)
app.get('/api/run-frequency-stream', authenticate, async (req, res) => {
    try {
        const { domain, device, region, mode, minFrequency, clusterId } = req.query;
        if (!domain) return res.status(400).json({ error: 'domain required' });

        const normalizedDomain = normalizeUrl(domain);
        const settings = await getSystemSettings();

        // Calculate cost: frequency_rate RUB per keyword
        let queryCount = 0;
        let queryStr = "SELECT COUNT(*) as count FROM yandex_queries WHERE user_id = ? AND site_url = ? AND minus_word = 0";
        let queryParams = [req.user.user_id, normalizedDomain];

        if (mode === 'missing') {
            queryStr += " AND (frequency IS NULL OR frequency = 0)";
        }
        
        if (clusterId && clusterId !== '0') {
            queryStr += " AND clustered = ?";
            queryParams.push(clusterId);
        }

        const [rows] = await db.query(queryStr, queryParams);
        queryCount = rows[0].count;

        if (queryCount > 0) {
            const cost = queryCount * settings.frequency_rate;
            await checkAndDeductBalance(req.user.user_id, cost, `Съем частоты ${queryCount} запросов (${normalizedDomain}, кластер: ${clusterId || 'все'}, режим: ${mode || 'all'})`);
        }
        
        // Create task
        const payload = JSON.stringify({ 
            domain: normalizedDomain, 
            device: device || '', 
            region: region || '', 
            mode: mode || 'all',
            minFrequency: minFrequency || '10',
            clusterId: clusterId || '0'
        });
        
        const [result] = await db.execute(
            "INSERT INTO tasks (user_id, task_type, payload) VALUES (?, ?, ?)",
            [req.user.user_id, 'frequency', payload]
        );
        
        res.json({ success: true, task_id: result.insertId });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Get task status
app.get('/api/tasks/:id', authenticate, async (req, res) => {
    try {
        const { id } = req.params;
        const [rows] = await db.execute(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
            [id, req.user.user_id]
        );
        
        if (rows.length === 0) {
            return res.status(404).json({ error: 'Task not found' });
        }
        
        res.json(rows[0]);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Background Tasks
const RUN_INTERVAL = 24 * 60 * 60 * 1000; // 24 hours

function startBackgroundTasks() {
    console.log('📦 Background tasks scheduler started');
    
    // Start Worker
    const workerPath = path.join(__dirname, '..', 'services', 'worker.py');
    const worker = spawn(PYTHON_PATH, [workerPath]);
    
    worker.stdout.on('data', (data) => console.log(`[Worker] ${data}`));
    worker.stderr.on('data', (data) => console.error(`[Worker Error] ${data}`));
    worker.on('close', (code) => console.log(`[Worker] Exited with code ${code}`));

    // Run once on start
    setTimeout(() => {
        runScheduler();
    }, 5000);

    // Schedule every 24h
    setInterval(() => {
        runScheduler();
    }, RUN_INTERVAL);
}

async function runScheduler() {
    try {
        console.log('🔄 Running daily query update...');
        const result = await callPython(
            path.join(__dirname, 'scripts', 'scheduler.py'),
            []
        );
        console.log('✅ Daily update finished:', result);
    } catch (error) {
        console.error('❌ Scheduler error:', error.message);
    }
}

// --- User Settings ---
app.get('/api/user/settings', authenticate, async (req, res) => {
    try {
        const [rows] = await db.query("SELECT yandex_region_id FROM user_settings WHERE user_id = ?", [req.user.user_id]);
        if (rows.length > 0) {
            res.json(rows[0]);
        } else {
            res.json({ yandex_region_id: 213 }); // Default to Moscow
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/user/settings', authenticate, async (req, res) => {
    try {
        const { yandex_region_id } = req.body;
        await db.query(
            "INSERT INTO user_settings (user_id, yandex_region_id) VALUES (?, ?) ON DUPLICATE KEY UPDATE yandex_region_id = ?",
            [req.user.user_id, yandex_region_id, yandex_region_id]
        );
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// API: Generate ideal structure
app.post('/api/cluster/generate-structure', authenticate, async (req, res) => {
    try {
        const { competitors_headers } = req.body;
        if (!competitors_headers) {
            return res.status(400).json({ error: 'Missing competitors_headers' });
        }
        
        const result = await callPython(
            path.join(__dirname, 'scripts', 'generate_structure.py'),
            [JSON.stringify({ competitors_headers })]
        );
        
        try {
            const jsonMatch = result.match(/\{.*\}/s);
            const data = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(result);
            res.json(data);
        } catch (parseError) {
            console.error('Parse error in generate-structure:', parseError, result);
            res.status(500).json({ error: 'Failed to parse AI response', raw: result });
        }
    } catch (error) {
        console.error('Error generating structure:', error);
        res.status(500).json({ error: error.message });
    }
});

// API: Save structure
app.post('/api/cluster/save-structure', authenticate, async (req, res) => {
    try {
        const { domain, clusterId, structure } = req.body;
        if (!domain || !clusterId || !structure) {
            return res.status(400).json({ error: 'Missing parameters' });
        }
        
        const normalizedDomain = normalizeUrl(domain);
        const [rows] = await db.query(
            "SELECT analysis_data FROM cluster_analysis WHERE user_id = ? AND site_url = ? AND cluster_id = ?",
            [req.user.user_id, normalizedDomain, clusterId]
        );
        
        if (rows.length === 0) {
            return res.status(404).json({ error: 'Analysis not found' });
        }
        
        const analysis = JSON.parse(rows[0].analysis_data);
        analysis.saved_structure = {
            data: structure,
            saved_at: new Date().toISOString()
        };
        
        await db.query(
            "UPDATE cluster_analysis SET analysis_data = ? WHERE user_id = ? AND site_url = ? AND cluster_id = ?",
            [JSON.stringify(analysis), req.user.user_id, normalizedDomain, clusterId]
        );
        
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Serve HTML
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Start tasks
startBackgroundTasks();

app.listen(PORT, () => {
    console.log(`Server: http://localhost:${PORT}`);
});