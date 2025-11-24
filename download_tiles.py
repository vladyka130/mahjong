"""
Скрипт для завантаження зображень плиток маджонгу
"""

import os
import urllib.request
from pathlib import Path

# Створюємо папку для зображень
assets_dir = Path("assets/tiles")
assets_dir.mkdir(parents=True, exist_ok=True)

print("📥 Завантаження зображень плиток маджонгу...")
print("\n💡 Інструкція:")
print("1. Відвідай один з цих ресурсів:")
print("   - https://opengameart.org/ (пошук: mahjong tiles)")
print("   - https://kenney.nl/assets (пошук: mahjong)")
print("   - https://itch.io/game-assets/free (пошук: mahjong tiles)")
print("\n2. Завантаж набір плиток")
print("3. Розпакуй у папку assets/tiles/")
print("\n4. Або використай готовий набір з GitHub:")
print("   https://github.com/search?q=mahjong+tiles+sprites")
print("\n📁 Папка створена: assets/tiles/")
print("\n💾 Після завантаження зображень, оновіть код main.py для їх використання")



