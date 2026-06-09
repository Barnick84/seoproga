import sys

with open('nodejs-app/public/analysis.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace('id="summaryStatsCard" style="display: none; margin-bottom: 24px;"', 'id="summaryStatsCard" style="margin-bottom: 24px;"')
html = html.replace('id="recommendationsCard" style="display: none;"', 'id="recommendationsCard"')
html = html.replace('id="top20ChartCard" style="display: none;"', 'id="top20ChartCard"')

with open('nodejs-app/public/analysis.html', 'w', encoding='utf-8') as f:
    f.write(html)
