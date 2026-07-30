import sys

with open('nodejs-app/public/analysis.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the topMenu with the new mainLayout
old_top_menu = '''    <div class="top-menu" id="topMenu" style="display:none;">
        <div class="user-info">
            <div class="logo">SEO Auto Cluster</div>
            <div class="balance-display">
                <span class="balance-label">Баланс:</span>
                <span class="balance-value">0.00 ₽</span>
                <button class="btn-topup-icon" onclick="showTopupModal()" title="Пополнить баланс">+</button>
            </div>
            <div class="menu-tabs">
                <a href="dashboard.html" class="menu-tab">Dashboard</a>
                <a href="sort.html" class="menu-tab">Сортировка</a>
                <a href="cluster.html" class="menu-tab">Кластер</a>
                <a href="positions.html" class="menu-tab">Позиции</a>
                <a href="cabinet.html" class="menu-tab">Кабинет</a>
            </div>
        </div>
        <div class="site-selector">
            <select id="siteSelect" onchange="selectSite()">
                <option value="">-- Выберите сайт --</option>
            </select>
            <button class="btn-add" onclick="showAddSiteModal()">+ Добавить сайт</button>
            <button class="btn-add" onclick="logout()" style="background:#555; margin-left:10px;">Выйти</button>
        </div>
    </div>'''

new_main_layout = '''    <div class="layout-wrapper" id="mainLayout" style="display:none;">
        <aside class="sidebar" id="sidebar">
            <div class="logo">SEO Auto Cluster</div>
            <div class="menu-tabs">
                <a href="dashboard.html" class="menu-tab">Dashboard</a>
                <a href="sort.html" class="menu-tab">Сортировка</a>
                <a href="cluster.html" class="menu-tab">Кластер</a>
                <a href="positions.html" class="menu-tab">Позиции</a>
                <a href="cabinet.html" class="menu-tab">Кабинет</a>
            </div>
        </aside>

        <main class="main-content">
            <header class="top-bar" id="topBar">
                <div class="balance-display">
                    <span class="balance-label">Баланс:</span>
                    <span class="balance-value">0.00 ₽</span>
                    <button class="btn-topup-icon" onclick="showTopupModal()" title="Пополнить баланс">+</button>
                </div>
                <div class="site-selector">
                    <select id="siteSelect" onchange="selectSite()">
                        <option value="">-- Выберите сайт --</option>
                    </select>
                    <button class="btn-add" onclick="showAddSiteModal()">+ Добавить сайт</button>
                    <button class="btn-add" onclick="logout()" style="background:#555; margin-left:10px;">Выйти</button>
                </div>
            </header>'''

# Because of line endings, let's normalise them for replacement
content = content.replace('\r\n', '\n')

if old_top_menu in content:
    content = content.replace(old_top_menu, new_main_layout)
    print("Replaced topMenu successfully")
else:
    print("Failed to find topMenu")

old_close = '''    </div>

    <div id="addSiteModal" class="modal">'''
new_close = '''        </div>
        </main>
    </div>

    <div id="addSiteModal" class="modal">'''

if old_close in content:
    content = content.replace(old_close, new_close)
    print("Replaced mainLayout close successfully")
else:
    print("Failed to find old close block")

# Save file
with open('nodejs-app/public/analysis.html', 'w', encoding='utf-8') as f:
    f.write(content)

