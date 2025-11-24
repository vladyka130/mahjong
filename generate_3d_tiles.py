"""
Скрипт для генерації 3D тейлів маджонгу з існуючих зображень
Додає тіні, градієнти та об'ємний ефект
"""

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from pathlib import Path
import os

def add_3d_effect(image_path: Path, output_path: Path):
    """Додає 3D ефект до зображення тейлу"""
    # Відкриваємо зображення
    img = Image.open(image_path).convert("RGBA")
    original_width, original_height = img.size
    
    # Створюємо нове зображення з додатковим простором для тіні
    padding = 10
    new_width = original_width + padding * 2
    new_height = original_height + padding * 2
    
    # Створюємо базове зображення з прозорим фоном
    result = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))
    
    # Створюємо тінь
    shadow = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    
    # Малюємо тінь (темна, зміщена вправо-вниз)
    shadow_x = padding + 3
    shadow_y = padding + 4
    shadow_draw.ellipse(
        [shadow_x, shadow_y, shadow_x + original_width, shadow_y + original_height],
        fill=(0, 0, 0, 80)  # Напівпрозора чорна тінь
    )
    
    # Розмиваємо тінь
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=5))
    
    # Додаємо тінь до результату
    result = Image.alpha_composite(result, shadow)
    
    # Створюємо градієнтний overlay для об'ємного вигляду
    gradient = Image.new("RGBA", (original_width, original_height), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    
    # Створюємо лінійний градієнт (світліший зверху, темніший знизу)
    for y in range(original_height):
        # Обчислюємо прозорість градієнта
        alpha = int(30 * (1 - y / original_height))  # Від 30 до 0
        if alpha > 0:
            # Верхня частина - світліша
            if y < original_height // 2:
                color = (255, 255, 255, alpha)
            # Нижня частина - темніша
            else:
                color = (0, 0, 0, alpha // 2)
            
            gradient_draw.line([(0, y), (original_width, y)], fill=color)
    
    # Застосовуємо градієнт до оригінального зображення
    img_with_gradient = Image.alpha_composite(img, gradient)
    
    # Додаємо об'ємний ефект через підсвітлення країв
    # Верхній край - світліший
    edge_overlay = Image.new("RGBA", (original_width, original_height), (0, 0, 0, 0))
    edge_draw = ImageDraw.Draw(edge_overlay)
    
    # Верхній край
    edge_draw.rectangle([0, 0, original_width, 3], fill=(255, 255, 255, 40))
    # Лівий край
    edge_draw.rectangle([0, 0, 3, original_height], fill=(255, 255, 255, 40))
    # Нижній край - темніший
    edge_draw.rectangle([0, original_height - 3, original_width, original_height], fill=(0, 0, 0, 30))
    # Правий край - темніший
    edge_draw.rectangle([original_width - 3, 0, original_width, original_height], fill=(0, 0, 0, 30))
    
    img_final = Image.alpha_composite(img_with_gradient, edge_overlay)
    
    # Вставляємо оброблене зображення в результат (з відступом для тіні)
    result.paste(img_final, (padding, padding), img_final)
    
    # Зберігаємо результат
    result.save(output_path, "PNG")
    print(f"✓ Оброблено: {image_path.name} -> {output_path.name}")


def process_all_tiles():
    """Обробляє всі тейли в папці tiles/"""
    # Шлях до папки з тейлами (як в main_flet.py)
    tiles_dir = Path("assets/tiles")
    
    # Якщо немає, пробуємо просто "tiles"
    if not tiles_dir.exists():
        tiles_dir = Path("tiles")
    
    if not tiles_dir.exists():
        print(f"❌ Папка {tiles_dir} не знайдена!")
        return
    
    # Створюємо папку для 3D тейлів (або використовуємо backup оригіналів)
    backup_dir = tiles_dir / "original_backup"
    output_dir = tiles_dir / "3d_tiles"
    
    # Створюємо папки, якщо їх немає
    backup_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    # Знаходимо всі PNG файли
    png_files = list(tiles_dir.glob("*.png"))
    
    if not png_files:
        print(f"❌ Не знайдено PNG файлів в {tiles_dir}")
        return
    
    print(f"📦 Знайдено {len(png_files)} файлів для обробки\n")
    
    # Обробляємо кожен файл
    for img_path in png_files:
        # Пропускаємо файли в підпапках
        if img_path.parent != tiles_dir:
            continue
        
        # Створюємо backup оригіналу
        backup_path = backup_dir / img_path.name
        if not backup_path.exists():
            import shutil
            shutil.copy2(img_path, backup_path)
            print(f"💾 Створено backup: {backup_path.name}")
        
        # Генеруємо 3D версію
        output_path = output_dir / img_path.name
        try:
            add_3d_effect(img_path, output_path)
        except Exception as e:
            print(f"❌ Помилка при обробці {img_path.name}: {e}")
    
    print(f"\n✅ Готово! 3D тейли збережено в {output_dir}")
    print(f"💡 Оригінали збережено в {backup_dir}")
    print(f"\n📝 Наступні кроки:")
    print(f"   1. Перевірте результат в {output_dir}")
    print(f"   2. Якщо все добре, скопіюйте файли з {output_dir} в {tiles_dir}")
    print(f"   3. Або оновіть код для використання папки 3d_tiles")


if __name__ == "__main__":
    try:
        process_all_tiles()
    except ImportError:
        print("❌ Помилка: не встановлено бібліотеку Pillow")
        print("💡 Встановіть: pip install Pillow")
    except Exception as e:
        print(f"❌ Помилка: {e}")

