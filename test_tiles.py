"""
Тестовий скрипт для перевірки завантаження зображень плиток
"""

from pathlib import Path
import sys
import codecs

# Виправлення кодування для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Додаємо поточну директорію до шляху для імпорту
sys.path.insert(0, str(Path(__file__).parent))

from main import TileType, Game

print("🔍 Перевірка завантаження зображень плиток...")
print("=" * 60)

# Створюємо екземпляр гри (це завантажить зображення)
try:
    game = Game()
    
    print(f"\n📊 Статистика завантаження:")
    print(f"   Всього типів плиток: {len(TileType)}")
    print(f"   Завантажено зображень: {len(game.tile_images)}")
    
    # Перевіряємо, які зображення знайдені
    tiles_dir = Path("assets/tiles")
    if tiles_dir.exists():
        png_files = list(tiles_dir.glob("*.png"))
        print(f"   Файлів PNG у папці: {len(png_files)}")
        
        # Перевіряємо основні типи
        print(f"\n✅ Перевірка основних типів:")
        test_tiles = [
            (TileType.BAMBOO_1, "Sou1.png"),
            (TileType.DOT_1, "Pin1.png"),
            (TileType.WAN_1, "Man1.png"),
            (TileType.EAST, "Ton.png"),
            (TileType.RED_DRAGON, "Chun.png"),
        ]
        
        for tile_type, expected_file in test_tiles:
            if tile_type in game.tile_images:
                print(f"   ✅ {tile_type.name}: знайдено")
            else:
                print(f"   ❌ {tile_type.name}: не знайдено (очікувався {expected_file})")
    
    print("\n" + "=" * 60)
    print("💡 Якщо всі зображення завантажені, гра готова до запуску!")
    print("   Запусти: python main.py")
    
except Exception as e:
    print(f"❌ Помилка: {e}")
    import traceback
    traceback.print_exc()

