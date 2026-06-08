import os

html_dir = r"C:\Users\BarNick\Desktop\seo-auto-cluster\nodejs-app\public"

EMOJI_MAP = {
    "\U0001f680": '<i class="fas fa-rocket"></i>',  # 🚀
    "\u2705": '<i class="fas fa-check-circle"></i>',  # ✅
    "\u274c": '<i class="fas fa-times-circle"></i>',  # ❌
    "\u26a0\ufe0f": '<i class="fas fa-exclamation-triangle"></i>',  # ⚠️
    "\u26a0": '<i class="fas fa-exclamation-triangle"></i>',  # ⚠ (no VS)
    "\U0001f310": '<i class="fas fa-globe"></i>',  # 🌐
    "\U0001f4ca": '<i class="fas fa-chart-bar"></i>',  # 📊
    "\u23f3": '<i class="fas fa-hourglass-half"></i>',  # ⏳
    "\U0001f4c8": '<i class="fas fa-chart-line"></i>',  # 📈
    "\U0001f504": '<i class="fas fa-sync-alt"></i>',  # 🔄
    "\u2795": '<i class="fas fa-plus"></i>',  # ➕
    "\u2715": '<i class="fas fa-times"></i>',  # ✕
    "\U0001f5d1\ufe0f": '<i class="fas fa-trash-alt"></i>',  # 🗑️
    "\U0001f5d1": '<i class="fas fa-trash-alt"></i>',  # 🗑 (no VS)
    "\U0001f441\ufe0f": '<i class="fas fa-eye"></i>',  # 👁️
    "\U0001f441": '<i class="fas fa-eye"></i>',  # 👁 (no VS)
    "\u2728": '<i class="fas fa-wand-magic-sparkles"></i>',  # ✨
    "\U0001f4be": '<i class="fas fa-save"></i>',  # 💾
    "\u2699\ufe0f": '<i class="fas fa-cog"></i>',  # ⚙️
    "\u2699": '<i class="fas fa-cog"></i>',  # ⚙ (no VS)
    "\U0001f50d": '<i class="fas fa-search"></i>',  # 🔍
    "\U0001f4a1": '<i class="fas fa-lightbulb"></i>',  # 💡
    "\U0001f517": '<i class="fas fa-link"></i>',  # 🔗
    "\U0001f4cc": '<i class="fas fa-thumbtack"></i>',  # 📌
    "\u2b50": '<i class="fas fa-star"></i>',  # ⭐
    "\U0001f4c1": '<i class="fas fa-folder"></i>',  # 📁
    "\U0001f4dd": '<i class="fas fa-pen"></i>',  # 📝
    "\u270f\ufe0f": '<i class="fas fa-pencil-alt"></i>',  # ✏️
    "\u270f": '<i class="fas fa-pencil-alt"></i>',  # ✏ (no VS)
    "\U0001f5a5": '<i class="fas fa-desktop"></i>',  # 🖥
    "\U0001f4f1": '<i class="fas fa-mobile-alt"></i>',  # 📱
    "\U0001f4cb": '<i class="fas fa-clipboard"></i>',  # 📋
    "\U0001f4cd": '<i class="fas fa-map-marker-alt"></i>',  # 📍
    "\U0001f4e5": '<i class="fas fa-download"></i>',  # 📥
    "\U0001f464": '<i class="fas fa-user"></i>',  # 👤
    "\u26aa": '<i class="far fa-circle"></i>',  # ⚪
}

files = sorted(f for f in os.listdir(html_dir) if f.endswith(".html"))

for fname in files:
    path = os.path.join(html_dir, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    for emoji, replacement in EMOJI_MAP.items():
        content = content.replace(emoji, replacement)

    if content != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated: {fname}")
    else:
        print(f"No changes: {fname}")

print("\nDone!")
