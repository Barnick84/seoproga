import sys

with open('nodejs-app/public/analysis.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update the toolbar
old_toolbar = '''            <div style="display: flex; gap: 10px; align-items: center;">
                <button class="btn btn-secondary" id="btnCollectKeywords" onclick="collectKeywordsForCluster()">Собрать ключи</button>
                <button class="btn btn-secondary" id="btnCheckPositions" onclick="checkPositions()">Позиции</button>
                <button class="btn btn-secondary" id="btnFrequency" onclick="showFrequencyModal()">Частота</button>
                <button class="btn btn-secondary" title="Настройки съема" onclick="showSettingsModal()"><i class="fas fa-cog"></i></button>
                <button class="btn btn-secondary" id="btnSetTargetUrl" onclick="showTargetUrlModal()">URL
                    страницы</button>
                <button class="btn btn-primary" id="btnSeoAnalysis" onclick="startSeoAnalysis()">SEO анализ</button>
                <button class="btn btn-secondary" id="btnPublish" style="display: none;">Опубликовать</button>
            </div>'''

new_toolbar = '''            <div class="toolbar-panel" style="display: flex; gap: 10px; align-items: center; background: #eef2ff; padding: 12px 20px; border-radius: 8px; border: 1px solid #c7d2fe; box-shadow: 0 4px 6px rgba(0,0,0,0.05); flex-wrap: wrap;">
                <button class="btn btn-secondary" id="btnCollectKeywords" onclick="collectKeywordsForCluster()">Собрать ключи</button>
                <button class="btn btn-secondary" id="btnCheckPositions" onclick="checkPositions()">Позиции</button>
                <button class="btn btn-secondary" id="btnFrequency" onclick="showFrequencyModal()">Частота</button>
                <button class="btn btn-secondary" title="Настройки съема" onclick="showSettingsModal()"><i class="fas fa-cog"></i></button>
                <button class="btn btn-secondary" id="btnSetTargetUrl" onclick="showTargetUrlModal()">URL страницы</button>
                <button class="btn btn-primary" id="btnSeoAnalysis" onclick="startSeoAnalysis()">SEO анализ</button>
                <button class="btn btn-secondary" id="btnPublish" style="display: none;">Опубликовать</button>
            </div>'''

if old_toolbar in html:
    html = html.replace(old_toolbar, new_toolbar)
else:
    print('Failed to find toolbar')

# 2. Extract contents from tab-summary
basic_stats = '''            <div class="card">
                <h2>Основные показатели текста</h2>
                <div style="display: flex; gap: 15px; margin-bottom: 20px;">
                    <div id="intentDisplay" style="padding: 10px 20px; border-radius: 8px; font-weight: bold; background: #eef2ff; color: #4338ca;">Интент: ...</div>
                </div>
                <div class="metrics-grid" id="summaryGrid">
                    <!-- Dynamic Summary Metrics -->
                </div>
            </div>'''

top_20 = '''            <div class="card" id="top20ChartCard">
                <h2>Топ-20 слов по плотности (%)</h2>
                <div id="top20DensityContainer" style="height: 400px; width: 100%;"></div>
            </div>'''

recommendations = '''            <div class="card">
                <h2>Рекомендации</h2>
                <div id="recommendationsList" class="metrics-grid" style="grid-template-columns: 1fr;">
                    <!-- Recommendations -->
                </div>
            </div>'''

tab_summary_full = f'''        <!-- Summary Tab -->
        <div id="tab-summary" class="tab-content active">
{basic_stats}

{top_20}

{recommendations}
        </div>'''

if tab_summary_full in html:
    html = html.replace(tab_summary_full, '''        <!-- Summary Tab removed, contents moved -->
        <div id="tab-summary" class="tab-content" style="display: none;"></div>''')
else:
    print('Failed to find tab-summary')

# 3. Update tabs list
old_tabs = '''        <div class="tabs">
            <div class="tab active" onclick="switchTab(this, 'summary')">Сводка</div>
            <div class="tab" onclick="switchTab(this, 'tech')">Тех. аудит</div>'''

new_tabs = '''        <div class="tabs">
            <div class="tab active" onclick="switchTab(this, 'tech')">Тех. аудит</div>'''

if old_tabs in html:
    html = html.replace(old_tabs, new_tabs)
else:
    print('Failed to find tabs list')

# 4. Update tab-tech to be active
old_tab_tech = '''        <!-- Technical Audit Tab -->
        <div id="tab-tech" class="tab-content">'''

new_tab_tech = '''        <!-- Technical Audit Tab -->
        <div id="tab-tech" class="tab-content active">'''

if old_tab_tech in html:
    html = html.replace(old_tab_tech, new_tab_tech)
else:
    print('Failed to find tab-tech')

# 5. Insert basic_stats before detailsKeywords
details_kw = '''        <div class="container" style="margin-bottom: 24px;">
            <details id="detailsKeywords"'''

new_details_kw = f'''        <div class="container" style="margin-bottom: 24px;">
{basic_stats.replace('            ', '            ').replace('<div class="card">', '<div class="card" id="summaryStatsCard" style="display: none; margin-bottom: 24px;">')}

            <details id="detailsKeywords"'''

if details_kw in html:
    html = html.replace(details_kw, new_details_kw)
else:
    print('Failed to find detailsKeywords')

# 6. Insert recommendations after detailsLsi
details_lsi_end = '''                <div id="clusterLsiList" style="margin-top: 10px;">
                    Загрузка...
                </div>
            </details>
        </div>'''

new_details_lsi_end = f'''                <div id="clusterLsiList" style="margin-top: 10px;">
                    Загрузка...
                </div>
            </details>

{recommendations.replace('<div class="card">', '<div class="card" id="recommendationsCard" style="display: none;">')}
        </div>'''

if details_lsi_end in html:
    html = html.replace(details_lsi_end, new_details_lsi_end)
else:
    print('Failed to find detailsLsi end')

# 7. Insert top_20 at the very bottom
end_main_app = '''    </div>

    <div id="addSiteModal" class="modal">'''

new_end_main_app = f'''{top_20.replace('            ', '        ').replace('top20ChartCard"', 'top20ChartCard" style="display: none;"')}
    </div>

    <div id="addSiteModal" class="modal">'''

if end_main_app in html:
    html = html.replace(end_main_app, new_end_main_app)
else:
    print('Failed to find end_main_app')

with open('nodejs-app/public/analysis.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Done')
