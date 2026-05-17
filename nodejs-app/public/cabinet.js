
/* cabinet.js */

async function loadCabinetData() {
    try {
        const res = await authFetch('/api/user/settings');
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `HTTP ${res.status}`);
        }
        const data = await res.json();
        
        if (data.success) {
            // Render sites
            renderSites(data.sites);
            
            // Set Yandex token
            if (data.yandex_token) {
                document.getElementById('yandexToken').value = data.yandex_token;
            }

            // Load billing history
            loadBillingHistory();
        } else {
            showCabinetStatus(data.error || 'Ошибка: сервер вернул success:false', 'error');
        }
    } catch (e) {
        console.error('CABINET_LOAD_ERROR:', e);
        showCabinetStatus('Ошибка при загрузке данных: ' + e.message, 'error');
    }
}

async function loadBillingHistory() {
    try {
        const res = await authFetch('/api/billing-history');
        const data = await res.json();
        if (data.success) {
            renderBillingHistory(data.billing);
            renderPaymentHistory(data.payments);
        }
    } catch (e) {
        console.error('Failed to load billing history:', e);
    }
}

function renderBillingHistory(history) {
    const body = document.getElementById('billingHistoryBody');
    if (!body) return;
    
    if (!history || history.length === 0) {
        body.innerHTML = '<tr><td colspan="3" class="empty-state">Нет операций</td></tr>';
        return;
    }
    
    body.innerHTML = history.map(item => `
        <tr>
            <td>${new Date(item.created_at).toLocaleString('ru-RU')}</td>
            <td>${item.description}</td>
            <td class="history-amount ${item.type}">
                ${item.type === 'deposit' ? '+' : '-'}${parseFloat(item.amount).toLocaleString('ru-RU')} ₽
            </td>
        </tr>
    `).join('');
}

function renderPaymentHistory(payments) {
    const body = document.getElementById('paymentHistoryBody');
    if (!body) return;
    
    if (!payments || payments.length === 0) {
        body.innerHTML = '<tr><td colspan="4" class="empty-state">Нет пополнений</td></tr>';
        return;
    }
    
    body.innerHTML = payments.map(item => `
        <tr>
            <td>${new Date(item.created_at).toLocaleString('ru-RU')}</td>
            <td><code>${item.order_id}</code></td>
            <td class="history-amount deposit">${parseFloat(item.amount).toLocaleString('ru-RU')} ₽</td>
            <td><span class="status-badge ${item.status}">${item.status === 'success' ? 'Оплачен' : 'Ожидание'}</span></td>
        </tr>
    `).join('');
}

function renderSites(sites) {
    const list = document.getElementById('sitesList');
    if (!list) return;
    
    if (!sites || sites.length === 0) {
        list.innerHTML = '<div class="empty-state">Нет подключенных сайтов</div>';
        return;
    }
    
    list.innerHTML = '';
    sites.forEach(site => {
        const item = document.createElement('div');
        item.className = 'site-item';
        item.innerHTML = `
            <span class="domain">${site}</span>
            <span class="status-tag">Подключен</span>
        `;
        list.appendChild(item);
    });
}

async function changePassword() {
    const current = document.getElementById('currentPassword').value;
    const newPass = document.getElementById('newPassword').value;
    const confirm = document.getElementById('confirmPassword').value;
    
    if (!current || !newPass || !confirm) {
        showCabinetStatus('Заполните все поля для смены пароля', 'error');
        return;
    }
    
    if (newPass !== confirm) {
        showCabinetStatus('Новые пароли не совпадают', 'error');
        return;
    }
    
    if (newPass.length < 6) {
        showCabinetStatus('Новый пароль должен быть не менее 6 символов', 'error');
        return;
    }
    
    try {
        const res = await authFetch('/api/user/change-password', {
            method: 'POST',
            body: JSON.stringify({
                current_password: current,
                new_password: newPass
            })
        });
        const data = await res.json();
        
        if (data.success) {
            showCabinetStatus('Пароль успешно изменен', 'success');
            document.getElementById('currentPassword').value = '';
            document.getElementById('newPassword').value = '';
            document.getElementById('confirmPassword').value = '';
        } else {
            showCabinetStatus(data.error || 'Ошибка при смене пароля', 'error');
        }
    } catch (e) {
        showCabinetStatus('Ошибка сервера', 'error');
    }
}

async function saveSettings() {
    const token = document.getElementById('yandexToken').value.trim();
    
    try {
        const res = await authFetch('/api/user/settings', {
            method: 'POST',
            body: JSON.stringify({ yandex_token: token })
        });
        const data = await res.json();
        
        if (data.success) {
            showCabinetStatus('Настройки Яндекс.Вебмастера сохранены', 'success');
        } else {
            showCabinetStatus('Ошибка при сохранении настроек', 'error');
        }
    } catch (e) {
        showCabinetStatus('Ошибка сервера', 'error');
    }
}

function showCabinetStatus(msg, type) {
    const el = document.getElementById('cabinetStatus');
    if (!el) return;
    
    el.textContent = msg;
    el.className = 'alert alert-' + type;
    el.style.display = 'block';
    
    // Auto-hide after 5 seconds if success
    if (type === 'success') {
        setTimeout(() => {
            el.style.display = 'none';
        }, 5000);
    }
}

// Custom hook for site selection in cabinet
function onSiteSelected(domain) {
    // If we are in cabinet, we don't necessarily need to reload everything,
    // but maybe we want to highlight the selected site or similar.
    // For now, just logging.
    console.log('Site selected in cabinet:', domain);
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    // Wait a bit for session check in app.js
    setTimeout(() => {
        const session = localStorage.getItem('session');
        if (session) {
            loadCabinetData();
        }
    }, 500);
});
