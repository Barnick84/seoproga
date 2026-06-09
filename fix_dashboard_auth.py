import re

path = '/home/barnick/seo-auto-cluster/nodejs-app/public/dashboard.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

guard = """
    <script>
        /* Auth guard: dashboard.html is deprecated — redirect appropriately */
        (async function() {
            var session = localStorage.getItem('session');
            if (!session) {
                window.location.replace('/');
                return;
            }
            try {
                var res = await fetch('/api/auth/session', { headers: { 'Authorization': session } });
                var data = await res.json();
                if (data.authenticated) {
                    window.location.replace('/sort.html' + window.location.search);
                } else {
                    localStorage.removeItem('session');
                    window.location.replace('/');
                }
            } catch(e) {
                window.location.replace('/');
            }
        })();
    </script>"""

marker = '</head>'
if 'Auth guard: dashboard.html is deprecated' not in content:
    content = content.replace(marker, guard + '\n' + marker, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('dashboard.html patched OK')
else:
    print('dashboard.html already patched')
