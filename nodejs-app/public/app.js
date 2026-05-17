/* public/app.js */
let currentDomain = '';
let keywords = [];
let userBalance = 0;
let minusWords = [];
let clusterMappings = {};
let clusterAnalysis = {};
let currentUser = '';
let collapsedClusters = new Set();
let selectedSidebarClusterId = null;
let addedSites = [];

async function checkSession() {
    const session = localStorage.getItem('session');
    const isIndexPage = window.location.pathname.endsWith('index.html') || window.location.pathname === '/' || window.location.pathname === '';
    
    if (!session) {
        if (!isIndexPage) {
            window.location.href = 'index.html';
            return;
        }
        showAuthSection(true);
        return;
    }
    
    try {
        const res = await fetch('/api/auth/session', {
            headers: { 'Authorization': session }
        });
        const data = await res.json();
        
    if (data.authenticated) {
            currentUser = data.username;
            fetchUserInfo(); // Fetch balance
            showMainApp();
            
            // Check for add-site action in URL
            if (isIndexPage) {
                const params = new URLSearchParams(window.location.search);
                if (params.get('action') === 'add-site') {
                    // Small delay to ensure everything is loaded
                    setTimeout(() => showAddSiteModal(), 500);
                    // Clean URL
                    const url = new URL(window.location);
                    url.searchParams.delete('action');
                    window.history.replaceState({}, '', url);
                }
            }
        } else {
            if (!isIndexPage) {
                window.location.href = 'index.html';
                return;
            }
            showAuthSection(true);
        }
    } catch (e) {
        console.log('Session check failed');
        if (!isIndexPage) {
            window.location.href = 'index.html';
            return;
        }
        showAuthSection(true);
    }
}

async function fetchUserInfo() {
    try {
        const res = await authFetch('/api/user-info');
        const data = await res.json();
        if (data.success) {
            userBalance = data.user.balance;
            updateBalanceUI();
        }
    } catch (e) {
        console.error('Failed to fetch user info:', e);
    }
}

function updateBalanceUI() {
    const balanceElements = document.querySelectorAll('.balance-value');
    balanceElements.forEach(el => {
        el.textContent = parseFloat(userBalance).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) + ' ₽';
    });
}

function showTopupModal() {
    const modal = document.getElementById('topupModal');
    if (modal) modal.classList.add('visible');
}

function closeTopupModal() {
    const modal = document.getElementById('topupModal');
    if (modal) modal.classList.remove('visible');
}

function setTopupAmount(amount) {
    const input = document.getElementById('topupAmount');
    if (input) input.value = amount;
}

async function startPayment() {
    const amountInput = document.getElementById('topupAmount');
    const amount = parseInt(amountInput.value);
    
    if (!amount || amount < 500) {
        alert('Минимальная сумма пополнения 500 руб.');
        return;
    }
    
    try {
        const btn = document.getElementById('btnStartPayment');
        const originalText = btn.textContent;
        btn.textContent = 'Загрузка...';
        btn.disabled = true;

        const res = await authFetch('/api/create-payment', {
            method: 'POST',
            body: JSON.stringify({ amount })
        });
        
        const data = await res.json();
        if (data.success && data.payment_url) {
            window.location.href = data.payment_url;
        } else {
            alert(data.error || 'Ошибка при создании платежа');
        }
        
        btn.textContent = originalText;
        btn.disabled = false;
    } catch (e) {
        alert('Ошибка соединения с сервером');
        console.error(e);
        const btn = document.getElementById('btnStartPayment');
        if (btn) btn.disabled = false;
    }
}

function showAuthSection(show) {
    const auth = document.getElementById('authSection');
    const app = document.getElementById('mainApp');
    const menu = document.getElementById('topMenu');
    if (auth) auth.style.display = show ? 'block' : 'none';
    if (app) app.style.display = show ? 'none' : 'block';
    if (menu) menu.style.display = show ? 'none' : 'flex';
}

function showMainApp() {
    showAuthSection(false);
    loadSites();
    
    // Adjust "Add Site" button based on page
    const isIndexPage = window.location.pathname.endsWith('index.html') || window.location.pathname === '/' || window.location.pathname === '';
    if (!isIndexPage) {
        const btnAdd = document.querySelector('.btn-add[onclick="showAddSiteModal()"]');
        if (btnAdd) {
            btnAdd.outerHTML = `<a href="index.html?action=add-site" class="btn-add" style="text-decoration:none; display:inline-flex; align-items:center; justify-content:center;">+ Добавить сайт</a>`;
        }
    }
}

async function loadSites() {
    const session = localStorage.getItem('session');
    if (!session) return;

    try {
        const res = await fetch('/api/sites', {
            headers: { 'Authorization': session }
        });
        
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            console.error('Failed to load sites:', res.status, errData);
            if (res.status === 401) {
                localStorage.removeItem('session');
                window.location.reload();
            }
            return;
        }

        const data = await res.json();
        console.log('Sites loaded:', data);
        
        addedSites = (data.sites || []).map(s => s.domain);
        
        const select = document.getElementById('siteSelect');
        if (!select) return;
        
        select.innerHTML = '<option value="">-- Выберите сайт --</option>';
        
        const noSitesMsg = document.getElementById('noSitesMessage');
        const sitesContent = document.getElementById('sitesContent');
        
        if (!data.sites || data.sites.length === 0) {
            if (noSitesMsg) noSitesMsg.style.display = 'block';
            if (sitesContent) sitesContent.style.display = 'none';
            // Populate Hero select
            fetchAndPopulateSiteSelect('newSiteDomainHero');
        } else {
            if (noSitesMsg) noSitesMsg.style.display = 'none';
            if (sitesContent) sitesContent.style.display = 'block';
            
            data.sites.forEach(site => {
                const opt = document.createElement('option');
                opt.value = site.domain;
                opt.textContent = site.domain;
                select.appendChild(opt);
            });
        }
        
        const params = new URLSearchParams(window.location.search);
        const savedDomain = params.get('site') || params.get('domain');
        if (savedDomain) {
            select.value = savedDomain;
            currentDomain = savedDomain;
            selectSite();
        }
    } catch (e) {
        console.error('Error in loadSites:', e);
    }
}

function selectSite() {
    const domain = document.getElementById('siteSelect').value;
    const url = new URL(window.location);
    if (domain) {
        url.searchParams.set('site', domain);
        currentDomain = domain;
    } else {
        url.searchParams.delete('site');
        currentDomain = '';
    }
    window.history.replaceState({}, '', url);
    
    // Update all menu tabs to include the site parameter
    document.querySelectorAll('.menu-tab').forEach(tab => {
        const tabUrl = new URL(tab.href, window.location.origin);
        if (domain) {
            tabUrl.searchParams.set('site', domain);
        } else {
            tabUrl.searchParams.delete('site');
        }
        tab.href = tabUrl.pathname + tabUrl.search;
    });

    if (typeof onSiteSelected === 'function') onSiteSelected(domain);
}

function showStatus(msg, type) {
    const el = document.getElementById('status');
    if (!el) return;
    el.textContent = msg;
    el.className = 'status ' + type;
    el.style.display = 'block';

    if (el._hideTimeout) clearTimeout(el._hideTimeout);
    
    if (type === 'success') {
        el._hideTimeout = setTimeout(() => {
            el.style.display = 'none';
        }, 10000);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function logout() {
    const session = localStorage.getItem('session');
    if (session) {
        await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Authorization': session }
        });
    }
    localStorage.removeItem('session');
    location.href = 'index.html';
}

function showAuthForm(type) {
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    const tabs = document.querySelectorAll('.auth-tab');
    if (type === 'login' && tabs[0]) tabs[0].classList.add('active');
    if (type === 'register' && tabs[1]) tabs[1].classList.add('active');
    
    const loginForm = document.getElementById('authForm');
    const regForm = document.getElementById('registerFields');
    if (loginForm) loginForm.style.display = type === 'login' ? 'block' : 'none';
    if (regForm) regForm.style.display = type === 'register' ? 'block' : 'none';
}

async function submitAuth() {
    const username = document.getElementById('authUsername').value;
    const password = document.getElementById('authPassword').value;
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (data.success) {
            localStorage.setItem('session', data.session);
            location.reload();
        } else {
            const err = document.getElementById('authError');
            if (err) {
                err.textContent = data.error;
                err.style.display = 'block';
            }
        }
    } catch (e) {
        console.error(e);
    }
}

async function submitRegister() {
    const username = document.getElementById('authUsernameReg').value.trim();
    const email = document.getElementById('authEmailReg').value.trim();
    const yandex_token = document.getElementById('authYandexTokenReg').value.trim();
    const password = document.getElementById('authPasswordReg').value;
    const passwordConfirm = document.getElementById('authPasswordConfirmReg').value;
    
    if (password !== passwordConfirm) {
        alert('Пароли не совпадают');
        return;
    }
    
    try {
        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email, yandex_token })
        });
        const data = await res.json();
        if (data.success) {
            localStorage.setItem('session', data.session);
            location.reload();
        } else {
            alert(data.error);
        }
    } catch (e) {
        console.error(e);
    }
}

function togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const toggle = input.nextElementSibling;
    if (input.type === 'password') {
        input.type = 'text';
        toggle.textContent = '🙈';
    } else {
        input.type = 'password';
        toggle.textContent = '👁️';
    }
}

async function showAddSiteModal() {
    const modal = document.getElementById('addSiteModal');
    if (modal) modal.classList.add('visible');
    fetchAndPopulateSiteSelect('newSiteDomain');
}

async function fetchAndPopulateSiteSelect(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = '<option value="">Загрузка...</option>';
    
    try {
        const res = await authFetch('/api/get-wm-hosts');
        const data = await res.json();
        
        if (data.success && data.hosts && data.hosts.length > 0) {
            // Filter out already added sites
            const filteredHosts = data.hosts.filter(host => {
                let url = host.unicode_host_url || host.host_id;
                if (url.endsWith('/')) url = url.slice(0, -1);
                const normalized = url.replace(/^https?:\/\//, '').toLowerCase();
                return !addedSites.some(s => s.toLowerCase() === normalized);
            });

            if (filteredHosts.length === 0) {
                select.innerHTML = '<option value="">Все ваши сайты уже добавлены</option>';
                return;
            }

            select.innerHTML = '<option value="">-- Выберите сайт из Вебмастера --</option>';
            filteredHosts.forEach(host => {
                const opt = document.createElement('option');
                let url = host.unicode_host_url || host.host_id;
                if (url.endsWith('/')) url = url.slice(0, -1);
                
                opt.value = url;
                opt.textContent = url;
                select.appendChild(opt);
            });
        } else {
            select.innerHTML = `<option value="">${data.error || 'Доступных сайтов не найдено'}</option>`;
            if (!data.success && data.error === 'Yandex token not found') {
                select.innerHTML = '<option value="">Токен Яндекса не установлен в Кабинете</option>';
            }
        }
    } catch (e) {
        console.error('Fetch hosts failed:', e);
        select.innerHTML = '<option value="">Ошибка загрузки сайтов</option>';
    }
}

function hideAddSiteModal() {
    const modal = document.getElementById('addSiteModal');
    if (modal) modal.classList.remove('visible');
}

async function addSite() {
    const select = document.getElementById('newSiteDomain');
    const domain = select ? select.value : '';
    if (!domain) {
        alert('Пожалуйста, выберите сайт из списка');
        return;
    }
    
    const res = await authFetch('/api/sites', {
        method: 'POST',
        body: JSON.stringify({domain})
    });
    const data = await res.json();
    if (data.success) {
        location.reload();
    } else {
        alert(data.message || 'Ошибка при добавлении сайта');
    }
}

// Sidebar triggers
function updateSidebarVisibility() {
    const selectedKwsCount = document.querySelectorAll('.kw-checkbox:checked').length;
    const sidebar = document.getElementById('clusteringSidebar');
    if (!sidebar) return;
    
    // Only open the sidebar if keywords are selected.
    // Do NOT close it here if selectedKwsCount === 0.
    if (selectedKwsCount > 0) {
        sidebar.classList.add('open');
        if (typeof updateSidebarClusterList === 'function') updateSidebarClusterList();
    }
}

function closeSidebar() {
    const sidebar = document.getElementById('clusteringSidebar');
    if (sidebar) sidebar.classList.remove('open');
    if (typeof deselectClusterAll === 'function') deselectClusterAll();
}

async function authFetch(url, options = {}) {
    const session = localStorage.getItem('session');
    const headers = {
        'Authorization': session || '',
        ...options.headers
    };
    
    if (options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    
    return fetch(url, { ...options, headers });
}

// Initialization on load
document.addEventListener('DOMContentLoaded', () => {
    checkSession();
});
