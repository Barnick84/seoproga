import glob
html_files = glob.glob('api/public/*.html')
for file in html_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('style.css?v=4.1', 'style.css?v=4.2')
    content = content.replace('app.js?v=4.1', 'app.js?v=4.2')
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
print('Updated html files to v4.2')
