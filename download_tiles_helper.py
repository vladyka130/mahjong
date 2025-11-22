"""
Помічник для завантаження зображень плиток маджонгу
"""

import os
import sys
import urllib.request
import zipfile
from pathlib import Path

# Виправлення кодування для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def download_file(url: str, dest_path: Path):
    """Завантажує файл з URL"""
    try:
        print(f"📥 Завантаження {url}...")
        urllib.request.urlretrieve(url, dest_path)
        print(f"✅ Завантажено: {dest_path}")
        return True
    except Exception as e:
        print(f"❌ Помилка завантаження: {e}")
        return False

def extract_zip(zip_path: Path, extract_to: Path):
    """Розпаковує ZIP архів"""
    try:
        print(f"📦 Розпаковка {zip_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"✅ Розпаковано у {extract_to}")
        return True
    except Exception as e:
        print(f"❌ Помилка розпаковки: {e}")
        return False

def main():
    """Головна функція"""
    tiles_dir = Path("assets/tiles")
    tiles_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("🀄 Завантаження зображень плиток маджонгу")
    print("=" * 60)
    print("\n💡 Автоматичне завантаження може бути складним через різні ліцензії.")
    print("   Краще завантажити вручну з одного з цих ресурсів:\n")
    
    print("📚 Рекомендовані ресурси:")
    print("   1. OpenGameArt.org: https://opengameart.org/")
    print("      Пошук: 'mahjong tiles'")
    print()
    print("   2. Kenney.nl: https://kenney.nl/assets")
    print("      Пошук: 'mahjong'")
    print()
    print("   3. Itch.io: https://itch.io/game-assets/free")
    print("      Пошук: 'mahjong tiles'")
    print()
    print("   4. GitHub: https://github.com/search?q=mahjong+tiles+sprites")
    print()
    
    print("📁 Після завантаження:")
    print(f"   - Розпакуй архів (якщо потрібно)")
    print(f"   - Скопіюй PNG файли у папку: {tiles_dir.absolute()}")
    print(f"   - Переконайся, що назви файлів відповідають формату")
    print(f"     (див. {tiles_dir}/README.md для деталей)")
    print()
    
    print("🔍 Альтернатива: створи власні зображення")
    print("   Можна використати будь-який графічний редактор")
    print("   Рекомендований розмір: 60x80 пікселів")
    print()
    
    # Перевіряємо, чи є вже якісь файли
    existing_files = list(tiles_dir.glob("*.png"))
    if existing_files:
        print(f"✅ Знайдено {len(existing_files)} зображень у папці")
        for f in existing_files[:5]:  # Показуємо перші 5
            print(f"   - {f.name}")
        if len(existing_files) > 5:
            print(f"   ... та ще {len(existing_files) - 5}")
    else:
        print("⚠️  Зображення не знайдено. Гра буде використовувати placeholder'и.")
    
    print("\n" + "=" * 60)
    print("💡 Підказка: гра працює і без зображень!")
    print("   Запусти main.py, щоб побачити placeholder'и з текстом.")
    print("=" * 60)

if __name__ == "__main__":
    main()

