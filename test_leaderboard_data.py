"""
Тестовий скрипт для перевірки збереження даних про підказки та тасування
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from main_flet import (
    load_encrypted_db,
    save_encrypted_db,
    fetch_leaderboard,
    start_session,
    end_session,
    insert_profile_record,
    create_profile,
    authenticate,
)

def test_leaderboard_data():
    """Тестує збереження даних про підказки та тасування"""
    print("=" * 60)
    print("ТЕСТ: Перевірка збереження даних про підказки та тасування")
    print("=" * 60)
    
    # Знаходимо або створюємо тестового користувача
    test_username = "test_leaderboard"
    test_password = "test123"
    
    # Спробуємо автентифікувати користувача
    profile = authenticate(test_username, test_password)
    
    if profile:
        profile_id = profile["id"]
        print(f"[OK] Знайдено користувача: {test_username} (id={profile_id})")
    else:
        # Створюємо нового користувача
        profile = create_profile(test_username, test_password)
        if profile:
            profile_id = profile["id"]
            print(f"[OK] Створено нового користувача: {test_username} (id={profile_id})")
        else:
            print("[ERROR] Помилка: не вдалося створити користувача")
            return
    
    # Очищаємо старі тестові дані (опціонально)
    print("\nОчищаємо старі тестові дані...")
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM records WHERE profile_id = ?", (profile_id,))
    cursor.execute("DELETE FROM sessions WHERE profile_id = ?", (profile_id,))
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)
    print("[OK] Старі дані видалено")
    
    # Симулюємо гру з використанням підказок та тасування
    print("\n" + "=" * 60)
    print("СИМУЛЯЦІЯ ГРИ")
    print("=" * 60)
    
    # 1. Створюємо сесію
    session_id = start_session(profile_id)
    print(f"[OK] Створено сесію: id={session_id}")
    
    # 2. Симулюємо час гри (5 хвилин 30 секунд = 330 секунд)
    game_duration = 330
    hints_used = 1  # Використано 1 підказку
    shuffle_used = 1  # Використано 1 тасування
    
    # 3. Завершуємо сесію (це встановить end_time)
    end_time = end_session(session_id, "win", hints_used, shuffle_used)
    print(f"[OK] Завершено сесію: end_time={end_time}, hints_used={hints_used}, shuffle_used={shuffle_used}")
    
    # 4. Створюємо запис з тим самим timestamp
    insert_profile_record(profile_id, game_duration, end_time)
    print(f"[OK] Створено запис: duration={game_duration}, timestamp={end_time}")
    
    # 5. Перевіряємо дані в БД
    print("\n" + "=" * 60)
    print("ПЕРЕВІРКА ДАНИХ В БД")
    print("=" * 60)
    
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Перевіряємо сесію
    cursor.execute(
        "SELECT hints_used, shuffle_used, end_time FROM sessions WHERE id = ?",
        (session_id,)
    )
    session_data = cursor.fetchone()
    if session_data:
        print(f"[OK] Сесія в БД: hints_used={session_data[0]}, shuffle_used={session_data[1]}, end_time={session_data[2]}")
    else:
        print("[ERROR] Сесія не знайдена в БД!")
    
    # Перевіряємо запис
    cursor.execute(
        "SELECT timestamp, duration FROM records WHERE profile_id = ? ORDER BY timestamp DESC LIMIT 1",
        (profile_id,)
    )
    record_data = cursor.fetchone()
    if record_data:
        print(f"[OK] Запис в БД: timestamp={record_data[0]}, duration={record_data[1]}")
    else:
        print("[ERROR] Запис не знайдений в БД!")
    
    conn.close()
    save_encrypted_db(db_path)
    
    # 6. Перевіряємо fetch_leaderboard
    print("\n" + "=" * 60)
    print("ПЕРЕВІРКА fetch_leaderboard()")
    print("=" * 60)
    
    leaderboard = fetch_leaderboard(limit=10)
    
    found = False
    for entry in leaderboard:
        if entry["username"] == test_username:
            found = True
            print(f"\n[OK] Знайдено запис для {test_username}:")
            print(f"  - Найкращий час: {entry['best_time']}")
            print(f"  - Підказки: {entry['hints_used']}")
            print(f"  - Тасування: {entry['shuffle_used']}")
            
            if entry['hints_used'] == hints_used and entry['shuffle_used'] == shuffle_used:
                print("\n" + "=" * 60)
                print("[SUCCESS] ТЕСТ ПРОЙДЕНО УСПІШНО!")
                print("=" * 60)
                print(f"Дані про підказки ({hints_used}) та тасування ({shuffle_used}) правильно збережені та відображаються!")
            else:
                print("\n" + "=" * 60)
                print("[FAIL] ТЕСТ НЕ ПРОЙДЕНО!")
                print("=" * 60)
                print(f"Очікувалось: hints={hints_used}, shuffle={shuffle_used}")
                print(f"Отримано: hints={entry['hints_used']}, shuffle={entry['shuffle_used']}")
            break
    
    if not found:
        print(f"\n[ERROR] Запис для {test_username} не знайдено в лідерборді!")
        print("Всі записи в лідерборді:")
        for entry in leaderboard:
            print(f"  - {entry['username']}: {entry['best_time']}, hints={entry['hints_used']}, shuffle={entry['shuffle_used']}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_leaderboard_data()

