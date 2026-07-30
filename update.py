import glob
html_files = glob.glob('api/public/*.html')
for file in html_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    content = content.replace('style.css?v=4.0', 'style.css?v=4.1')
    content = content.replace('app.js?v=4.0', 'app.js?v=4.1')
    content = content.replace('src="app.js"', 'src="app.js?v=4.1"')
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
print('Updated html files')
