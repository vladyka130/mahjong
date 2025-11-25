"""
Mahjong Solitaire Game на Flet
Класична гра-головоломка з плитками маджонгу
"""

import flet as ft
import json
import random
import threading
import time
import asyncio
import sqlite3
import hashlib
import secrets
from pathlib import Path
from enum import Enum
from typing import Any, List, Tuple, Optional, Dict
from collections import deque
from datetime import datetime

# Умовний імпорт winsound (тільки на Windows)
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False
    winsound = None

# Константи
TILE_WIDTH = 50
TILE_HEIGHT = 70
TILE_SPACING_X = 51  # Щільно, але без накладання (ширина плитки 50px)
TILE_SPACING_Y = 71  # Щільно, але без накладання (висота плитки 70px)
SOLITAIRE2_SLOTS_OFFSET_RIGHT = 100  # Статичний відступ комірок вправо для Пасьянс 2

# Глобальна змінна для режиму гри
game_mode: str = "solitaire1"  # За замовчуванням - Пасьянс 1
# Поточний патерн, з яким запущена гра (для збереження рекордів по патернах)
current_pattern_name: Optional[str] = None

# Кольори (Flet формат)
BACKGROUND_COLOR = "#145014"
TILE_COLOR = "#FFFEF0"
SELECTED_COLOR = "#FFD700"
AVAILABLE_COLOR = "#90EE90"
BLOCKED_COLOR = "#646464"
UI_PANEL_COLOR = "#1E1E1E"
TEXT_COLOR = "#FFFFFF"
HINT_COLOR = "#FFC864"

RECORDS_FILE = Path("records.json")
DB_FILE_ENC = Path("mahjong_db.enc")
DB_FILE_PLAIN = Path("mahjong_db.tmp")
DB_SECRET_KEY = b"mahjong-super-secret-key-2025"
REMEMBER_FILE = Path("remember_me.dat")
HINT_LIMIT = 2
SHUFFLE_LIMIT = 1

def load_game_records_from_disk() -> List[dict]:
    """Підвантажує збережені рекорди з диска (JSON)"""
    if not RECORDS_FILE.exists():
        return []
    try:
        payload = json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload[:5]
    except Exception:
        pass
    return []


def save_game_records_to_disk(records: List[dict]):
    """Зберігає список рекордів у JSON-файл"""
    try:
        RECORDS_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def load_encrypted_db() -> Path:
    """Дешифрує файл бази sqlite у тимчасовий файл та повертає шлях"""
    if not DB_FILE_ENC.exists():
        # create empty sqlite database and encrypt it
        conn = sqlite3.connect(DB_FILE_PLAIN)
        conn.close()
        encrypted = _xor_encrypt(DB_FILE_PLAIN.read_bytes(), DB_SECRET_KEY)
        DB_FILE_ENC.write_bytes(encrypted)
        DB_FILE_PLAIN.unlink()
    encrypted = DB_FILE_ENC.read_bytes()
    DB_FILE_PLAIN.write_bytes(_xor_encrypt(encrypted, DB_SECRET_KEY))
    return DB_FILE_PLAIN


def save_encrypted_db(db_path: Path):
    """Шифрує sqlite файл та видаляє тимчасовий"""
    data = db_path.read_bytes()
    DB_FILE_ENC.write_bytes(_xor_encrypt(data, DB_SECRET_KEY))
    db_path.unlink(missing_ok=True)


def save_remembered_credentials(username: str, password: str):
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    REMEMBER_FILE.write_bytes(_xor_encrypt(payload, DB_SECRET_KEY))


def load_remembered_credentials() -> Optional[Dict[str, str]]:
    if not REMEMBER_FILE.exists():
        return None
    try:
        raw = REMEMBER_FILE.read_bytes()
        payload = _xor_encrypt(raw, DB_SECRET_KEY)
        data = json.loads(payload.decode("utf-8"))
        if "username" in data and "password" in data:
            return data
    except Exception:
        pass
    return None


def clear_remembered_credentials():
    if REMEMBER_FILE.exists():
        REMEMBER_FILE.unlink(missing_ok=True)


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def initialize_db():
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            coins INTEGER DEFAULT 10,
            hints INTEGER DEFAULT 0,
            shuffles INTEGER DEFAULT 0,
            role TEXT DEFAULT 'user',
            email TEXT
        )
        """
    )
    # Додаємо поле coins для існуючих користувачів, якщо його немає
    try:
        cursor.execute("ALTER TABLE profiles ADD COLUMN coins INTEGER DEFAULT 10")
    except sqlite3.OperationalError:
        pass  # Колонка вже існує
    # Оновлюємо coins для користувачів, у яких coins NULL
    cursor.execute("UPDATE profiles SET coins = 10 WHERE coins IS NULL")
    # Додаємо поля hints та shuffles для існуючих користувачів
    try:
        cursor.execute("ALTER TABLE profiles ADD COLUMN hints INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE profiles ADD COLUMN shuffles INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # Додаємо поле role для існуючих користувачів, якщо його немає
    try:
        cursor.execute("ALTER TABLE profiles ADD COLUMN role TEXT DEFAULT 'user'")
    except sqlite3.OperationalError:
        pass
    # Додаємо поле email для існуючих користувачів, якщо його немає
    try:
        cursor.execute("ALTER TABLE profiles ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass
    # Оновлюємо hints та shuffles для користувачів, у яких вони NULL
    cursor.execute("UPDATE profiles SET hints = 0 WHERE hints IS NULL")
    cursor.execute("UPDATE profiles SET shuffles = 0 WHERE shuffles IS NULL")
    cursor.execute("UPDATE profiles SET role = 'user' WHERE role IS NULL")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            duration INTEGER NOT NULL,
            game_mode TEXT,
            pattern_name TEXT,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        )
        """
    )
    # Додаємо поле game_mode для існуючих записів, якщо його немає
    try:
        cursor.execute("ALTER TABLE records ADD COLUMN game_mode TEXT")
    except sqlite3.OperationalError:
        pass  # Колонка вже існує
    # Додаємо поле pattern_name для існуючих записів, якщо його немає
    try:
        cursor.execute("ALTER TABLE records ADD COLUMN pattern_name TEXT")
    except sqlite3.OperationalError:
        pass  # Колонка вже існує
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            result TEXT,
            hints_used INTEGER,
            shuffle_used INTEGER,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        )
        """
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)


def _hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return dk.hex(), salt.hex()


def create_profile(username: str, password: str, email: Optional[str] = None) -> Optional[Dict]:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    password_hash, salt = _hash_password(password)
    try:
        cursor.execute(
            """
            INSERT INTO profiles (username, password_hash, salt, created_at, coins, hints, shuffles, role, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (username, password_hash, salt, datetime.now().isoformat(), 10, 0, 0, "user", email),
        )
    except sqlite3.IntegrityError:
        conn.close()
        save_encrypted_db(db_path)
        return None
    profile_id = cursor.lastrowid
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)
    return {"id": profile_id, "username": username, "role": "user"}


def ensure_admin_profile():
    """Гарантує наявність адміністративного облікового запису admin/admin."""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM profiles WHERE username = ?", ("admin",))
    row = cursor.fetchone()
    if row:
        conn.close()
        save_encrypted_db(db_path)
        return

    # Створюємо адмінський профіль з роллю admin
    password_hash, salt = _hash_password("admin")
    cursor.execute(
        """
        INSERT INTO profiles (username, password_hash, salt, created_at, coins, hints, shuffles, role, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("admin", password_hash, salt, datetime.now().isoformat(), 10, 0, 0, "admin", None),
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)


def authenticate(username: str, password: str) -> Optional[Dict]:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, password_hash, salt, role FROM profiles WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()
    save_encrypted_db(db_path)
    if not row:
        return None
    profile_id, stored_hash, salt_hex, role = row
    candidate_hash, _ = _hash_password(password, bytes.fromhex(salt_hex))
    if candidate_hash != stored_hash:
        return None
    # Якщо роль з якоїсь причини None, вважаємо звичайним користувачем
    if role is None:
        role = "user"
    return {"id": profile_id, "username": username, "role": role}


def change_user_password(profile_id: int, old_password: str, new_password: str) -> bool:
    """Змінює пароль користувача, якщо старий пароль введено правильно."""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT password_hash, salt FROM profiles WHERE id = ?",
        (profile_id,),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        save_encrypted_db(db_path)
        return False
    stored_hash, salt_hex = row
    candidate_hash, _ = _hash_password(old_password, bytes.fromhex(salt_hex))
    if candidate_hash != stored_hash:
        conn.close()
        save_encrypted_db(db_path)
        return False

    # Оновлюємо пароль
    new_hash, new_salt = _hash_password(new_password)
    cursor.execute(
        "UPDATE profiles SET password_hash = ?, salt = ? WHERE id = ?",
        (new_hash, new_salt, profile_id),
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)
    return True


def record_new_session(profile_id: int, result: str, hints_used: int, shuffle_used: int):
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO sessions (profile_id, start_time, end_time, result, hints_used, shuffle_used)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            profile_id,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            result,
            hints_used,
            shuffle_used,
        ),
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)


def fetch_profile_records(profile_id: int) -> List[dict]:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, duration FROM records WHERE profile_id = ? ORDER BY timestamp DESC LIMIT 5",
        (profile_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    save_encrypted_db(db_path)
    return [{"timestamp": r[0], "time": format_duration(r[1]), "duration": r[1]} for r in rows]


def insert_profile_record(
    profile_id: int,
    duration: int,
    timestamp: Optional[str] = None,
    game_mode: Optional[str] = None,
    pattern_name: Optional[str] = None,
):
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO records (profile_id, timestamp, duration, game_mode, pattern_name) VALUES (?, ?, ?, ?, ?)",
        (profile_id, timestamp, duration, game_mode, pattern_name),
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)


def get_user_coins(profile_id: int) -> int:
    """Отримує кількість монет користувача"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM profiles WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    save_encrypted_db(db_path)
    if row and row[0] is not None:
        return row[0]
    return 10  # Значення за замовчуванням

def get_user_hints(profile_id: int) -> int:
    """Отримує кількість підказок користувача"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT hints FROM profiles WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    save_encrypted_db(db_path)
    if row and row[0] is not None:
        return row[0]
    return 0

def get_user_shuffles(profile_id: int) -> int:
    """Отримує кількість тасувань користувача"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT shuffles FROM profiles WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    save_encrypted_db(db_path)
    if row and row[0] is not None:
        return row[0]
    return 0

def update_user_coins(profile_id: int, coins: int):
    """Оновлює кількість монет користувача"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET coins = ? WHERE id = ?", (coins, profile_id))
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)

def update_user_hints(profile_id: int, hints: int):
    """Оновлює кількість підказок користувача"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET hints = ? WHERE id = ?", (hints, profile_id))
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)

def update_user_shuffles(profile_id: int, shuffles: int):
    """Оновлює кількість тасувань користувача"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE profiles SET shuffles = ? WHERE id = ?", (shuffles, profile_id))
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)

def buy_hint(profile_id: int) -> bool:
    """Купує підказку за 1 coin. Повертає True якщо покупка успішна"""
    coins = get_user_coins(profile_id)
    if coins < 1:
        return False
    update_user_coins(profile_id, coins - 1)
    hints = get_user_hints(profile_id)
    update_user_hints(profile_id, hints + 1)
    return True

def buy_shuffle(profile_id: int) -> bool:
    """Купує тасування за 1 coin. Повертає True якщо покупка успішна"""
    coins = get_user_coins(profile_id)
    if coins < 1:
        return False
    update_user_coins(profile_id, coins - 1)
    shuffles = get_user_shuffles(profile_id)
    update_user_shuffles(profile_id, shuffles + 1)
    return True

def fetch_profile_stats(profile_id: int) -> Dict[str, Any]:
    """Повертає загальну статистику профілю та окремі кращі часи для Пасьянсу 1 і Пасьянсу 2."""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Загальна кількість ігор (усі режими)
    cursor.execute(
        "SELECT COUNT(*) FROM records WHERE profile_id = ?",
        (profile_id,),
    )
    row = cursor.fetchone()
    games = row[0] if row and row[0] is not None else 0

    # Кращий час для Пасьянсу 1 (старі записи без game_mode вважаємо Пасьянсом 1)
    cursor.execute(
        "SELECT MIN(duration) FROM records WHERE profile_id = ? AND (game_mode = 'solitaire1' OR game_mode IS NULL)",
        (profile_id,),
    )
    row = cursor.fetchone()
    best_s1 = row[0] if row and row[0] is not None else None

    # Кращий час для Пасьянсу 2
    cursor.execute(
        "SELECT MIN(duration) FROM records WHERE profile_id = ? AND game_mode = 'solitaire2'",
        (profile_id,),
    )
    row = cursor.fetchone()
    best_s2 = row[0] if row and row[0] is not None else None

    # Дата кращого рекорду (беремо дату найкращого з двох, для відображення в таблиці)
    best_date = None
    overall_best = None
    if best_s1 is not None and best_s2 is not None:
        overall_best = min(best_s1, best_s2)
    elif best_s1 is not None:
        overall_best = best_s1
    elif best_s2 is not None:
        overall_best = best_s2

    if overall_best is not None:
        cursor.execute(
            "SELECT timestamp FROM records WHERE profile_id = ? AND duration = ? ORDER BY timestamp DESC LIMIT 1",
            (profile_id, overall_best),
        )
        date_row = cursor.fetchone()
        if date_row:
            best_date = date_row[0]

    conn.close()
    save_encrypted_db(db_path)

    return {
        "games": games,
        "best_s1": best_s1,
        "best_s2": best_s2,
        "best_date": best_date,
    }


def fetch_pattern_best_time(
    profile_id: int, game_mode: str, pattern_name: str
) -> Optional[int]:
    """Повертає найкращий час для конкретного патерну та режиму, або None, якщо ігор не було."""
    if not pattern_name:
        return None
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT MIN(duration)
        FROM records
        WHERE profile_id = ?
          AND game_mode = ?
          AND pattern_name = ?
        """,
        (profile_id, game_mode, pattern_name),
    )
    row = cursor.fetchone()
    best = row[0] if row and row[0] is not None else None
    conn.close()
    save_encrypted_db(db_path)
    return best


def fetch_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    """Отримує список користувачів з їхнім кращим часом та даними про підказки і тасування"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Спочатку знаходимо найкращий час для кожного користувача
    cursor.execute(
        """
        SELECT 
            p.id,
            p.username,
            MIN(r.duration) AS best_time
        FROM profiles p
        LEFT JOIN records r ON p.id = r.profile_id
        GROUP BY p.id, p.username
        HAVING best_time IS NOT NULL
        ORDER BY best_time ASC, p.username ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    
    # Для кожного користувача знаходимо timestamp запису з найкращим часом та сесію
    leaderboard: List[Dict[str, Any]] = []
    for row in rows:
        profile_id, username, best_time = row
        hints_used = 0
        shuffle_used = 0
        
        if best_time is not None:
            # Знаходимо timestamp запису з найкращим часом
            cursor.execute(
                """
                SELECT timestamp
                FROM records
                WHERE profile_id = ? 
                  AND duration = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (profile_id, best_time),
            )
            timestamp_row = cursor.fetchone()
            best_time_timestamp = timestamp_row[0] if timestamp_row else None
            
            print(f"DEBUG fetch_leaderboard: profile_id={profile_id}, best_time={best_time}, timestamp={best_time_timestamp}")
            
            if best_time_timestamp:
                # Знаходимо сесію, яка найближча за часом до timestamp запису з найкращим часом
                # Дозволяємо різницю до 5 секунд через можливі округлення та затримки
                # result може бути "Виграш" або "win"
                cursor.execute(
                    """
                    SELECT hints_used, shuffle_used, end_time,
                           CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) AS session_duration
                    FROM sessions
                    WHERE profile_id = ? 
                      AND end_time IS NOT NULL 
                      AND (result = 'win' OR result = 'Виграш')
                      AND ABS(julianday(end_time) - julianday(?)) * 86400 <= 5
                    ORDER BY ABS(julianday(end_time) - julianday(?)) ASC
                    LIMIT 1
                    """,
                    (profile_id, best_time_timestamp, best_time_timestamp),
                )
                session_row = cursor.fetchone()
                
                # Якщо не знайшли за timestamp, шукаємо за duration
                if not session_row:
                    print(f"DEBUG fetch_leaderboard: Не знайдено сесію за timestamp для {username}, шукаю за duration")
                    cursor.execute(
                        """
                        SELECT hints_used, shuffle_used, end_time,
                               CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) AS session_duration
                        FROM sessions
                        WHERE profile_id = ? 
                          AND end_time IS NOT NULL 
                          AND (result = 'win' OR result = 'Виграш')
                          AND ABS(CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) - ?) <= 5
                        ORDER BY ABS(CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) - ?) ASC
                        LIMIT 1
                        """,
                        (profile_id, best_time, best_time),
                    )
                    session_row = cursor.fetchone()
            else:
                # Якщо немає timestamp, знаходимо сесію з найближчим duration
                cursor.execute(
                    """
                    SELECT hints_used, shuffle_used, end_time,
                           CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) AS session_duration
                    FROM sessions
                    WHERE profile_id = ? 
                      AND end_time IS NOT NULL 
                      AND (result = 'win' OR result = 'Виграш')
                      AND ABS(CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) - ?) <= 5
                    ORDER BY ABS(CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) - ?) ASC
                    LIMIT 1
                    """,
                    (profile_id, best_time, best_time),
                )
                session_row = cursor.fetchone()
            
            if session_row:
                hints_used = session_row[0] if session_row[0] is not None else 0
                shuffle_used = session_row[1] if session_row[1] is not None else 0
                session_end_time = session_row[2] if len(session_row) > 2 else None
                session_duration = session_row[3] if len(session_row) > 3 else None
                print(f"DEBUG fetch_leaderboard: Знайдено сесію для {username}: hints={hints_used}, shuffle={shuffle_used}, end_time={session_end_time}, duration={session_duration}")
            else:
                print(f"DEBUG fetch_leaderboard: Сесія не знайдена для {username} з best_time={best_time}, timestamp={best_time_timestamp}")
                # Додаткова діагностика - показуємо всі сесії для цього користувача
                cursor.execute(
                    """
                    SELECT id, hints_used, shuffle_used, end_time, result,
                           CAST((julianday(end_time) - julianday(start_time)) * 86400 AS INTEGER) AS session_duration
                    FROM sessions
                    WHERE profile_id = ? 
                      AND end_time IS NOT NULL 
                    ORDER BY end_time DESC
                    LIMIT 5
                    """,
                    (profile_id,),
                )
                all_sessions = cursor.fetchall()
                print(f"DEBUG fetch_leaderboard: Всі сесії для {username}: {all_sessions}")
        
        leaderboard.append(
            {
                "username": username,
                "best_time": best_time,
                "hints_used": hints_used,
                "shuffle_used": shuffle_used,
            }
        )
    
    conn.close()
    save_encrypted_db(db_path)
    print(f"DEBUG fetch_leaderboard: Повернуто {len(leaderboard)} користувачів")
    for entry in leaderboard:
        print(f"DEBUG fetch_leaderboard: {entry['username']} - {entry['best_time']}, hints={entry['hints_used']}, shuffle={entry['shuffle_used']}")
    return leaderboard

def start_session(profile_id: int) -> int:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sessions (profile_id, start_time)
        VALUES (?, ?)
        """,
        (profile_id, datetime.now().isoformat()),
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)
    return session_id


def end_session(session_id: int, result: str, hints_used: int, shuffle_used: int) -> str:
    """Завершує сесію і повертає end_time"""
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    end_time = datetime.now().isoformat()
    cursor.execute(
        """
        UPDATE sessions
        SET
            end_time = ?,
            result = ?,
            hints_used = ?,
            shuffle_used = ?
        WHERE id = ?
        """,
        (
            end_time,
            result,
            hints_used,
            shuffle_used,
            session_id,
        ),
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)
    return end_time



class TileType(Enum):
    """Типи плиток маджонгу"""
    # Бамбук (1-9)
    BAMBOO_1 = "b1"
    BAMBOO_2 = "b2"
    BAMBOO_3 = "b3"
    BAMBOO_4 = "b4"
    BAMBOO_5 = "b5"
    BAMBOO_6 = "b6"
    BAMBOO_7 = "b7"
    BAMBOO_8 = "b8"
    BAMBOO_9 = "b9"
    
    # Крапки (1-9)
    DOT_1 = "d1"
    DOT_2 = "d2"
    DOT_3 = "d3"
    DOT_4 = "d4"
    DOT_5 = "d5"
    DOT_6 = "d6"
    DOT_7 = "d7"
    DOT_8 = "d8"
    DOT_9 = "d9"
    
    # Ван (1-9)
    WAN_1 = "w1"
    WAN_2 = "w2"
    WAN_3 = "w3"
    WAN_4 = "w4"
    WAN_5 = "w5"
    WAN_6 = "w6"
    WAN_7 = "w7"
    WAN_8 = "w8"
    WAN_9 = "w9"
    
    # Вітри
    EAST = "east"
    SOUTH = "south"
    WEST = "west"
    NORTH = "north"
    
    # Дракони
    RED_DRAGON = "red_dragon"
    GREEN_DRAGON = "green_dragon"
    WHITE_DRAGON = "white_dragon"
    
    # Квіти/Сезони
    FLOWER_PLUM = "flower_plum"
    FLOWER_ORCHID = "flower_orchid"
    FLOWER_CHRYSANTHEMUM = "flower_chrys"
    FLOWER_BAMBOO = "flower_bamboo"
    SEASON_SPRING = "season_spring"
    SEASON_SUMMER = "season_summer"
    SEASON_AUTUMN = "season_autumn"
    SEASON_WINTER = "season_winter"


class Tile:
    """Клас для представлення однієї плитки"""
    
    def __init__(self, tile_type: TileType, x: int, y: int, z: int = 0):
        self.tile_type = tile_type
        self.x = x
        self.y = y
        self.z = z
        self.selected = False
        self.removed = False
        self.highlighted = False
        self.ui_element: Optional[ft.Container] = None
        
    def __eq__(self, other):
        """Дві плитки рівні, якщо вони одного типу"""
        if not isinstance(other, Tile):
            return False
        return self.tile_type == other.tile_type
    
    def get_display_name(self) -> str:
        """Повертає назву для відображення"""
        name_map = {
            TileType.BAMBOO_1: "1B", TileType.BAMBOO_2: "2B", TileType.BAMBOO_3: "3B",
            TileType.BAMBOO_4: "4B", TileType.BAMBOO_5: "5B", TileType.BAMBOO_6: "6B",
            TileType.BAMBOO_7: "7B", TileType.BAMBOO_8: "8B", TileType.BAMBOO_9: "9B",
            TileType.DOT_1: "1D", TileType.DOT_2: "2D", TileType.DOT_3: "3D",
            TileType.DOT_4: "4D", TileType.DOT_5: "5D", TileType.DOT_6: "6D",
            TileType.DOT_7: "7D", TileType.DOT_8: "8D", TileType.DOT_9: "9D",
            TileType.WAN_1: "1W", TileType.WAN_2: "2W", TileType.WAN_3: "3W",
            TileType.WAN_4: "4W", TileType.WAN_5: "5W", TileType.WAN_6: "6W",
            TileType.WAN_7: "7W", TileType.WAN_8: "8W", TileType.WAN_9: "9W",
            TileType.EAST: "東", TileType.SOUTH: "南", TileType.WEST: "西", TileType.NORTH: "北",
            TileType.RED_DRAGON: "中", TileType.GREEN_DRAGON: "發", TileType.WHITE_DRAGON: "白",
            TileType.FLOWER_PLUM: "梅", TileType.FLOWER_ORCHID: "蘭", 
            TileType.FLOWER_CHRYSANTHEMUM: "菊", TileType.FLOWER_BAMBOO: "竹",
            TileType.SEASON_SPRING: "春", TileType.SEASON_SUMMER: "夏",
            TileType.SEASON_AUTUMN: "秋", TileType.SEASON_WINTER: "冬",
        }
        return name_map.get(self.tile_type, "?")


class Board:
    """Клас для представлення дошки з плитками"""
    
    def __init__(self, pattern_name: Optional[str] = None):
        self.tiles: List[Tile] = []
        self.selected_tile: Optional[Tile] = None
        self.width = 20
        self.height = 10
        self.game_over = False
        self.selected_pattern_name: Optional[str] = pattern_name  # Вибраний патерн для solitaire2
        self.basic_tile_types = [
            TileType.BAMBOO_1, TileType.BAMBOO_2, TileType.BAMBOO_3, TileType.BAMBOO_4,
            TileType.BAMBOO_5, TileType.BAMBOO_6, TileType.BAMBOO_7, TileType.BAMBOO_8, TileType.BAMBOO_9,
            TileType.DOT_1, TileType.DOT_2, TileType.DOT_3, TileType.DOT_4,
            TileType.DOT_5, TileType.DOT_6, TileType.DOT_7, TileType.DOT_8, TileType.DOT_9,
            TileType.WAN_1, TileType.WAN_2, TileType.WAN_3, TileType.WAN_4,
            TileType.WAN_5, TileType.WAN_6, TileType.WAN_7, TileType.WAN_8, TileType.WAN_9,
            TileType.EAST, TileType.SOUTH, TileType.WEST, TileType.NORTH,
            TileType.RED_DRAGON, TileType.GREEN_DRAGON, TileType.WHITE_DRAGON,
            # Всі дракони мають унікальні файли:
            # RED_DRAGON -> pinyin1.png (червоний)
            # GREEN_DRAGON -> pinyin2.png (зелений)
            # WHITE_DRAGON -> pinyin16.png (жовтий)
            # Квіти та сезони
            TileType.FLOWER_PLUM, TileType.FLOWER_ORCHID, TileType.FLOWER_CHRYSANTHEMUM, TileType.FLOWER_BAMBOO,
            TileType.SEASON_SPRING, TileType.SEASON_SUMMER, TileType.SEASON_AUTUMN, TileType.SEASON_WINTER,
        ]
        self.generate_board()
        
    def generate_board(self):
        """Генерує дошку з плитками у вигляді патерну, повторюючи тасування поки є хід"""
        global game_mode
        pattern = self._create_pyramid_pattern()
        
        # Підраховуємо кількість місць для тейлів у патерні
        total_tile_positions = 0
        for layer in pattern:
            for row in layer:
                total_tile_positions += sum(1 for cell in row if cell)
        
        if game_mode == "solitaire2":
            # Для Пасьянс 2 використовуємо кількість з патерну
            # Якщо кількість непарна, додаємо один тейл для пари
            if total_tile_positions % 2 != 0:
                total_tile_positions += 1
                print(f"DEBUG generate_board: Кількість тейлів непарна, додано один тейл. Тепер: {total_tile_positions}")
            
            pair_count = total_tile_positions // 2
        else:
            # Для інших режимів - 100 пар (200 тейлів)
            pair_count = 100
        
        pair_choices = [random.choice(self.basic_tile_types) for _ in range(pair_count)]
        tiles = []
        for tile_type in pair_choices:
            tiles.extend([tile_type] * 2)

        max_attempts = 10
        self.game_over = False
        for attempt in range(max_attempts):
            self.tiles = []
            board_tiles = tiles.copy()
            random.shuffle(board_tiles)
            
            # Логування для діагностики (тільки для першої спроби)
            if attempt == 0:
                print(f"DEBUG generate_board: game_mode={game_mode}, pattern layers={len(pattern)}")
                for z, layer in enumerate(pattern):
                    tile_count = sum(sum(1 for cell in row if cell) for row in layer)
                    print(f"DEBUG generate_board: Шар {z}: {len(layer)} рядків, {tile_count} тейлів")
            
            tile_index = 0
            for z, layer in enumerate(pattern):
                for y, row in enumerate(layer):
                    for x, has_tile in enumerate(row):
                        if has_tile and tile_index < len(board_tiles):
                            self.tiles.append(Tile(board_tiles[tile_index], x, y, z))
                            tile_index += 1
            
            # Логування після розміщення (тільки для першої спроби)
            if attempt == 0:
                tiles_by_z = {}
                for tile in self.tiles:
                    tiles_by_z[tile.z] = tiles_by_z.get(tile.z, 0) + 1
                print(f"DEBUG generate_board: Розміщено тейлів по рівнях: {tiles_by_z}")

            if not self.is_game_lost():
                self.width = len(pattern[0][0])
                self.height = len(pattern[0])
                return

        print("WARNING: Не вдалося згенерувати дошку з ходом за", max_attempts, "спроб")
    
    def _create_pyramid_pattern(self) -> List[List[List[bool]]]:
        """Створює патерн з 1-3 шарами залежно від режиму"""
        global game_mode
        
        if game_mode == "solitaire2":
            # Для Пасьянс 2 використовуємо збережені патерни або класичний патерн "Turtle"
            # Якщо вказано конкретний патерн, завантажуємо його
            saved_pattern = self._load_random_saved_pattern(self.selected_pattern_name, "solitaire2")
            if saved_pattern:
                return saved_pattern
            # Якщо немає збережених патернів, використовуємо класичний патерн "Turtle"
            return self._create_turtle_pattern()
        elif game_mode == "solitaire1":
            # Для Пасьянс 1 використовуємо збережені патерни або стандартний патерн
            # Якщо вказано конкретний патерн, завантажуємо його
            saved_pattern = self._load_random_saved_pattern(self.selected_pattern_name, "solitaire1")
            if saved_pattern:
                return saved_pattern
            # Якщо немає збережених патернів, використовуємо стандартний патерн (один шар)
            layer0 = []
            for y in range(10):
                row = [True] * 20
                layer0.append(row)
            return [layer0]
        else:
            # Для інших режимів - один шар
            layer0 = []
            for y in range(10):
                row = [True] * 20
                layer0.append(row)
            return [layer0]
    
    def _load_random_saved_pattern(self, pattern_name: Optional[str] = None, game_mode_filter: Optional[str] = None) -> Optional[List[List[List[bool]]]]:
        """Завантажує збережений патерн. Якщо pattern_name вказано, завантажує конкретний патерн, інакше - випадковий.
        game_mode_filter - фільтр по типу пасьянсу (solitaire1/solitaire2)"""
        patterns_dir = Path("patterns")
        if not patterns_dir.exists():
            return None
        
        # Знаходимо всі JSON файли з патернами
        pattern_files = list(patterns_dir.glob("*.json"))
        if not pattern_files:
            return None
        
        # Фільтруємо патерни по типу пасьянсу, якщо вказано
        filtered_pattern_files = []
        for pf in pattern_files:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    pattern_data = json.load(f)
                if game_mode_filter:
                    # За замовчуванням вважаємо старі патерни як solitaire2 (історично конструктор був для Пасьянсу 2)
                    pattern_game_mode = pattern_data.get("game_mode", "solitaire2")
                    # Нормалізуємо можливі старі текстові значення
                    if pattern_game_mode in ("Пасьянс 1", "solitaire1"):
                        pattern_game_mode = "solitaire1"
                    elif pattern_game_mode in ("Пасьянс 2", "solitaire2"):
                        pattern_game_mode = "solitaire2"
                    if pattern_game_mode != game_mode_filter:
                        continue  # Пропускаємо патерни іншого типу
                filtered_pattern_files.append((pf, pattern_data))
            except:
                # Якщо не вдалося прочитати файл, пропускаємо його
                continue
        
        if not filtered_pattern_files:
            return None
        
        # Якщо вказано конкретний патерн, шукаємо його
        if pattern_name:
            pattern_file = None
            pattern_data = None
            for pf, pd in filtered_pattern_files:
                if pd.get("name", pf.stem) == pattern_name or pf.stem == pattern_name:
                    pattern_file = pf
                    pattern_data = pd
                    break
            
            if not pattern_file:
                print(f"DEBUG _load_random_saved_pattern: Патерн '{pattern_name}' не знайдено серед відфільтрованих патернів")
                return None
        else:
            # Вибираємо випадковий файл з відфільтрованих
            pattern_file, pattern_data = random.choice(filtered_pattern_files)
        
        try:
            # pattern_data вже завантажено вище
            
            # Перевіряємо структуру даних
            if "layers" not in pattern_data:
                print(f"DEBUG _load_random_saved_pattern: Некоректний формат файлу {pattern_file}")
                return None
            
            # Конвертуємо патерн у формат List[List[List[bool]]]
            layers = pattern_data["layers"]
            # Переконуємося, що це список списків списків булевих значень
            converted_layers = []
            for layer in layers:
                converted_layer = []
                for row in layer:
                    converted_row = [bool(cell) for cell in row]
                    converted_layer.append(converted_row)
                converted_layers.append(converted_layer)
            
            print(f"DEBUG _load_random_saved_pattern: Завантажено патерн '{pattern_data.get('name', 'unknown')}' з {len(converted_layers)} шарами")
            return converted_layers
        except Exception as e:
            print(f"DEBUG _load_random_saved_pattern: Помилка завантаження {pattern_file}: {e}")
            return None
    
    def _create_turtle_pattern(self) -> List[List[List[bool]]]:
        """Створює патерн схожий на скрін - більш щільний з меншими відступами"""
        pattern = []
        
        # Шар 0 (нижній) - найбільший, починається зверху
        layer0 = []
        # Починаємо одразу з тейлів (без відступів зверху)
        layer0.append([False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False])
        layer0.append([False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False])
        layer0.append([True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True])
        layer0.append([True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True])
        layer0.append([True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True])
        layer0.append([True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True])
        layer0.append([True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True])
        layer0.append([False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False])
        layer0.append([False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False])
        layer0.append([False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False])
        # Відступи знизу (1 рядок)
        layer0.append([False] * 18)
        pattern.append(layer0)
        
        # Шар 1 (середній) - менший, з невеликими відступами
        layer1 = []
        # Відступи зверху (1 рядок)
        layer1.append([False] * 18)
        # Основні рядки
        layer1.append([False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False])
        layer1.append([False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False])
        layer1.append([False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False])
        layer1.append([False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False])
        layer1.append([False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False])
        layer1.append([False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False])
        layer1.append([False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False])
        # Відступи знизу (1 рядок)
        layer1.append([False] * 18)
        pattern.append(layer1)
        
        # Шар 2 (верхній) - найменший
        layer2 = []
        # Відступи зверху (2 рядки)
        for y in range(2):
            layer2.append([False] * 18)
        # Основні рядки
        layer2.append([False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False])
        layer2.append([False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False])
        layer2.append([False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False])
        layer2.append([False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False])
        layer2.append([False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False])
        layer2.append([False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False])
        # Відступи знизу (2 рядки)
        for y in range(2):
            layer2.append([False] * 18)
        pattern.append(layer2)
        
        return pattern
    
    def is_tile_available(self, tile: Tile) -> bool:
        """Перевіряє, чи плитка доступна"""
        global game_mode
        
        if tile.removed:
            return False
        
        # Для Пасьянс-2: тейл доступний, якщо він відкритий зліва АБО справа (або з обох сторін)
        if game_mode == "solitaire2":
            # Перевіряємо, чи немає плиток зверху (на тому ж x, y, але вищий z)
            for other_tile in self.tiles:
                if other_tile.removed:
                    continue
                if other_tile.x == tile.x and other_tile.y == tile.y and other_tile.z > tile.z:
                    return False
            
            # Перевіряємо ліву та праву сторони
            def has_neighbor(dx: int, dy: int) -> bool:
                return any(
                    other_tile is not tile
                    and not other_tile.removed
                    and other_tile.z == tile.z
                    and other_tile.x == tile.x + dx
                    and other_tile.y == tile.y + dy
                    for other_tile in self.tiles
                )
            
            left_blocked = has_neighbor(-1, 0)  # Зліва
            right_blocked = has_neighbor(1, 0)  # Справа
            
            # Тейл доступний, якщо він відкритий зліва АБО справа (або з обох)
            # Якщо закритий і зліва, і справа - недоступний
            return not (left_blocked and right_blocked)
        
        # Для Пасьянс-1 та інших режимів - стандартна логіка
        # Перевіряємо, чи немає плиток зверху (на тому ж x, y, але вищий z)
        for other_tile in self.tiles:
            if other_tile.removed:
                continue
            if other_tile.x == tile.x and other_tile.y == tile.y and other_tile.z > tile.z:
                return False
        
        def has_neighbor(dx: int, dy: int) -> bool:
            return any(
                other_tile is not tile
                and not other_tile.removed
                and other_tile.z == tile.z
                and other_tile.x == tile.x + dx
                and other_tile.y == tile.y + dy
                for other_tile in self.tiles
            )

        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        # Якщо бодай один напрямок вільний — плитка доступна
        if any(not has_neighbor(dx, dy) for dx, dy in directions):
            return True

        def has_adjacent_same_type(dx: int, dy: int) -> bool:
            return any(
                other_tile is not tile
                and not other_tile.removed
                and other_tile.tile_type == tile.tile_type
                and other_tile.z == tile.z
                and other_tile.x == tile.x + dx
                and other_tile.y == tile.y + dy
                for other_tile in self.tiles
            )

        # Якщо поруч є плитка того ж типу — теж доступна
        return any(has_adjacent_same_type(dx, dy) for dx, dy in directions)

    def can_connect(self, tile1: Tile, tile2: Tile, max_turns: int = 2) -> bool:
        """Перевіряє, чи можна з’єднати дві плитки шляхом з <= max_turns поворотів"""
        if tile1 is tile2 or tile1.tile_type != tile2.tile_type:
            return False

        occupied = {
            (t.x, t.y)
            for t in self.tiles
            if not t.removed and t not in (tile1, tile2)
        }

        start = (tile1.x, tile1.y)
        dest = (tile2.x, tile2.y)
        directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        queue = deque([(start[0], start[1], None, 0)])
        seen = {(start[0], start[1], None): 0}

        def is_free(x: int, y: int) -> bool:
            if (x, y) == dest:
                return True
            if x < -1 or x > self.width or y < -1 or y > self.height:
                return False
            if x < 0 or x >= self.width or y < 0 or y >= self.height:
                return True
            return (x, y) not in occupied

        while queue:
            x, y, direction, turns = queue.popleft()
            if (x, y) == dest and turns <= max_turns:
                return True

            for dir_idx, (dx, dy) in enumerate(directions):
                nx, ny = x + dx, y + dy
                next_turns = turns + (0 if direction == dir_idx or direction is None else 1)
                if next_turns > max_turns or not is_free(nx, ny):
                    continue
                state = (nx, ny, dir_idx)
                prev_turns = seen.get(state)
                if prev_turns is not None and prev_turns <= next_turns:
                    continue
                seen[state] = next_turns
                queue.append((nx, ny, dir_idx, next_turns))

        return False
    
    def get_available_tiles(self) -> List[Tile]:
        """Повертає список доступних плиток"""
        return [tile for tile in self.tiles if self.is_tile_available(tile)]
    
    def clear_highlights(self):
        """Скидає стан підсвічування плиток"""
        for tile in self.tiles:
            tile.highlighted = False

    def find_hint_pair(self) -> Optional[Tuple[Tile, Tile]]:
        """Повертає першу пару плиток, яку можна з’єднати"""
        available = self.get_available_tiles()
        for i, tile1 in enumerate(available):
            for tile2 in available[i + 1 :]:
                if tile1 == tile2 and self.can_connect(tile1, tile2):
                    return tile1, tile2
        return None
    
    def click_tile(self, tile: Tile):
        """Обробляє клік по плитці"""
        global game_mode
        if self.game_over:
            return
        if tile.removed:
            return
        
        if not self.is_tile_available(tile):
            if self.selected_tile:
                self.selected_tile.selected = False
                self.selected_tile = None
            return
        
        # Для Пасьянс 1: дозволяємо виділяти будь-який доступний тейл, але видаляємо тільки однакові
        if game_mode == "solitaire1":
            if self.selected_tile is None:
                # Вибираємо перший тейл
                self.selected_tile = tile
                tile.selected = True
            elif self.selected_tile is tile:
                # Скасовуємо вибір, якщо клікнули на той самий тейл
                self.selected_tile.selected = False
                self.selected_tile = None
            elif self.selected_tile.tile_type == tile.tile_type:
                # Знайдено однакові тейли - перевіряємо, чи можна їх видалити
                selected_available = self.is_tile_available(self.selected_tile)
                clicked_available = self.is_tile_available(tile)
                can_connect_result = self.can_connect(self.selected_tile, tile)
                print(f"DEBUG click_tile solitaire1: selected_tile=({self.selected_tile.x},{self.selected_tile.y},{self.selected_tile.z}), tile_type={self.selected_tile.tile_type}")
                print(f"DEBUG click_tile solitaire1: clicked_tile=({tile.x},{tile.y},{tile.z}), tile_type={tile.tile_type}")
                print(f"DEBUG click_tile solitaire1: selected_available={selected_available}, clicked_available={clicked_available}, can_connect={can_connect_result}")
                if (
                    selected_available
                    and clicked_available
                    and can_connect_result
                ):
                    self.selected_tile.removed = True
                    tile.removed = True
                    self.selected_tile.selected = False
                    self.selected_tile = None
                else:
                    # Якщо не можна з'єднати, вибираємо новий тейл
                    print(f"DEBUG click_tile solitaire1: Не можна видалити пару - selected_available={selected_available}, clicked_available={clicked_available}, can_connect={can_connect_result}")
                    self.selected_tile.selected = False
                    self.selected_tile = tile
                    tile.selected = True
            else:
                # Вибираємо інший тейл
                self.selected_tile.selected = False
                self.selected_tile = tile
                tile.selected = True
        else:
            # Для Пасьянс 2 - нова логіка з комірками
            # Тейли прибираються по одному в комірки, а не парами одразу
            # selected_tile не використовується для solitaire2
            pass  # Логіка буде в tile_clicked
    
    def has_possible_moves(self) -> bool:
        """Чи є хоча б одна пара, яку можна з’єднати з <= max_turns поворотів"""
        available = self.get_available_tiles()
        if len(available) < 2:
            return False
        for i, tile1 in enumerate(available):
            for tile2 in available[i + 1 :]:
                if tile1 == tile2 and self.can_connect(tile1, tile2):
                    return True
        return False

    def reshuffle_remaining_tiles(self):
        """Перемішує типи плиток, залишаючи пусті клітинки порожніми"""
        remaining = [tile for tile in self.tiles if not tile.removed]
        if len(remaining) <= 1:
            return
        random.shuffle(remaining)
        pair_count = len(remaining) // 2
        pair_choices = [random.choice(self.basic_tile_types) for _ in range(pair_count)]
        tiles_pool: List[TileType] = []
        for tile_type in pair_choices:
            tiles_pool.extend([tile_type, tile_type])
        random.shuffle(tiles_pool)

        for tile, tile_type in zip(remaining, tiles_pool):
            tile.tile_type = tile_type
            tile.selected = False
            tile.highlighted = False
        self.selected_tile = None
        self.game_over = False
    
    def is_game_won(self) -> bool:
        """Перевіряє, чи виграна гра"""
        return all(tile.removed for tile in self.tiles)
    
    def is_game_lost(self) -> bool:
        """Перевіряє, чи програна гра (немає доступних ходів)"""
        return not self.has_possible_moves()


def main(page: ft.Page):
    """Головна функція Flet додатку"""
    page.title = "Mahjong Solitaire"
    # Встановлюємо розмір вікна, щоб поміщалося на більшості моніторів
    page.window.width = 1400
    page.window.height = 790  # Збільшено висоту на 30 пікселів, щоб прибрати скрол
    page.bgcolor = BACKGROUND_COLOR
    page.scroll = ft.ScrollMode.HIDDEN  # Прибрано скрол - висота статична
    page.padding = 0  # Прибрано padding, щоб не було пустого поля
    
    initialize_db()
    # Гарантуємо наявність облікового запису адміністратора (admin/admin)
    ensure_admin_profile()
    board = Board()
    
    # Завантаження зображень плиток
    tile_images = {}
    # Спочатку пробуємо папку з 3D тейлами (fulltiles), якщо немає - використовуємо оригінальну
    tiles_dir_3d = Path("assets/fulltiles")
    tiles_dir = Path("assets/tiles")
    
    # Вибираємо папку: спочатку 3D, якщо немає - оригінальна
    use_3d_tiles = tiles_dir_3d.exists() and any(tiles_dir_3d.glob("*.png"))
    
    if use_3d_tiles:
        tiles_dir = tiles_dir_3d
        print(f"✓ Використовую 3D тейли з {tiles_dir}")
        # Маппінг для нових назв файлів у папці fulltiles
        tile_file_mapping = {
            TileType.BAMBOO_1: ["bamboo1.png"],
            TileType.BAMBOO_2: ["bamboo2.png"],
            TileType.BAMBOO_3: ["bamboo3.png"],
            TileType.BAMBOO_4: ["bamboo4.png"],
            TileType.BAMBOO_5: ["bamboo5.png"],
            TileType.BAMBOO_6: ["bamboo6.png"],
            TileType.BAMBOO_7: ["bamboo7.png"],
            TileType.BAMBOO_8: ["bamboo8.png"],
            TileType.BAMBOO_9: ["bamboo9.png"],
            TileType.DOT_1: ["circle1.png"],
            TileType.DOT_2: ["circle2.png"],
            TileType.DOT_3: ["circle3.png"],
            TileType.DOT_4: ["circle4.png"],
            TileType.DOT_5: ["circle5.png"],
            TileType.DOT_6: ["circle6.png"],
            TileType.DOT_7: ["circle7.png"],
            TileType.DOT_8: ["circle8.png"],
            TileType.DOT_9: ["circle9.png"],
            TileType.WAN_1: ["pinyin13.png"],  # 一萬
            TileType.WAN_2: ["pinyin14.png"],  # 二萬
            TileType.WAN_3: ["pinyin15.png"],  # 三萬
            TileType.WAN_4: ["pinyin7.png"],   # 四萬
            TileType.WAN_5: ["pinyin8.png"],   # 伍萬
            TileType.WAN_6: ["pinyin9.png"],   # 六萬
            TileType.WAN_7: ["pinyin10.png"],  # 七萬
            TileType.WAN_8: ["pinyin11.png"],  # 八萬
            TileType.WAN_9: ["pinyin12.png"],  # 九萬
            TileType.EAST: ["pinyin4.png"],    # 東
            TileType.SOUTH: ["pinyin3.png"],   # 南
            TileType.WEST: ["pinyin6.png"],    # 西
            TileType.NORTH: ["pinyin5.png"],   # 北
            TileType.RED_DRAGON: ["pinyin1.png"],  # 中 (Chun) - червоний дракон
            TileType.GREEN_DRAGON: ["pinyin2.png"],  # 發 (Hatsu) - зелений дракон
            TileType.WHITE_DRAGON: ["pinyin16.png"],  # 白 (Haku) - білий/жовтий дракон (унікальний файл)
            # Квіти та сезони
            TileType.FLOWER_PLUM: ["peony.png"],
            TileType.FLOWER_ORCHID: ["orchid.png"],
            TileType.FLOWER_CHRYSANTHEMUM: ["chrysanthemum.png"],
            TileType.FLOWER_BAMBOO: ["lotus.png"],
            TileType.SEASON_SPRING: ["spring.png"],
            TileType.SEASON_SUMMER: ["summer.png"],
            TileType.SEASON_AUTUMN: ["fall.png"],
            TileType.SEASON_WINTER: ["winter.png"],
        }
    else:
        print(f"✓ Використовую оригінальні тейли з {tiles_dir}")
        # Старий маппінг для оригінальних тейлів
        tile_file_mapping = {
            TileType.BAMBOO_1: ["Sou1.png", "sou1.png", "SOU1.png"],
            TileType.BAMBOO_2: ["Sou2.png", "sou2.png", "SOU2.png"],
            TileType.BAMBOO_3: ["Sou3.png", "sou3.png", "SOU3.png"],
            TileType.BAMBOO_4: ["Sou4.png", "sou4.png", "SOU4.png"],
            TileType.BAMBOO_5: ["Sou5.png", "sou5.png", "SOU5.png"],
            TileType.BAMBOO_6: ["Sou6.png", "sou6.png", "SOU6.png"],
            TileType.BAMBOO_7: ["Sou7.png", "sou7.png", "SOU7.png"],
            TileType.BAMBOO_8: ["Sou8.png", "sou8.png", "SOU8.png"],
            TileType.BAMBOO_9: ["Sou9.png", "sou9.png", "SOU9.png"],
            TileType.DOT_1: ["Pin1.png", "pin1.png", "PIN1.png"],
            TileType.DOT_2: ["Pin2.png", "pin2.png", "PIN2.png"],
            TileType.DOT_3: ["Pin3.png", "pin3.png", "PIN3.png"],
            TileType.DOT_4: ["Pin4.png", "pin4.png", "PIN4.png"],
            TileType.DOT_5: ["Pin5.png", "pin5.png", "PIN5.png"],
            TileType.DOT_6: ["Pin6.png", "pin6.png", "PIN6.png"],
            TileType.DOT_7: ["Pin7.png", "pin7.png", "PIN7.png"],
            TileType.DOT_8: ["Pin8.png", "pin8.png", "PIN8.png"],
            TileType.DOT_9: ["Pin9.png", "pin9.png", "PIN9.png"],
            TileType.WAN_1: ["Man1.png", "man1.png", "MAN1.png"],
            TileType.WAN_2: ["Man2.png", "man2.png", "MAN2.png"],
            TileType.WAN_3: ["Man3.png", "man3.png", "MAN3.png"],
            TileType.WAN_4: ["Man4.png", "man4.png", "MAN4.png"],
            TileType.WAN_5: ["Man5.png", "man5.png", "MAN5.png"],
            TileType.WAN_6: ["Man6.png", "man6.png", "MAN6.png"],
            TileType.WAN_7: ["Man7.png", "man7.png", "MAN7.png"],
            TileType.WAN_8: ["Man8.png", "man8.png", "MAN8.png"],
            TileType.WAN_9: ["Man9.png", "man9.png", "MAN9.png"],
            TileType.EAST: ["Ton.png", "ton.png", "TON.png"],
            TileType.SOUTH: ["Nan.png", "nan.png", "NAN.png"],
            TileType.WEST: ["Shaa.png", "shaa.png", "SHAA.png"],
            TileType.NORTH: ["Pei.png", "pei.png", "PEI.png"],
            TileType.RED_DRAGON: ["Chun.png", "chun.png", "CHUN.png"],
            TileType.GREEN_DRAGON: ["Hatsu.png", "hatsu.png", "HATSU.png"],
            TileType.WHITE_DRAGON: ["Haku.png", "haku.png", "HAKU.png"],
        }
    
    if tiles_dir.exists():
        existing_files = {}
        for file_path in tiles_dir.glob("*.png"):
            existing_files[file_path.name.lower()] = file_path
        
        # Перевіряємо на конфлікти - один файл для кількох типів
        file_to_types = {}  # file -> list of tile_types
        for tile_type, possible_names in tile_file_mapping.items():
            for filename in possible_names:
                file_key = filename.lower()
                if file_key not in file_to_types:
                    file_to_types[file_key] = []
                file_to_types[file_key].append(tile_type)
        
        # Виводимо попередження про конфлікти
        for file_key, types in file_to_types.items():
            if len(types) > 1:
                print(f"WARNING: Файл {file_key} використовується для кількох типів тейлів: {[t.name for t in types]}")
        
        for tile_type, possible_names in tile_file_mapping.items():
            for filename in possible_names:
                file_path = tiles_dir / filename
                if file_path.exists() or filename.lower() in existing_files:
                    if filename.lower() in existing_files:
                        file_path = existing_files[filename.lower()]
                    try:
                        tile_images[tile_type] = str(file_path)
                        print(f"DEBUG load_tiles: {tile_type.name} -> {file_path.name}")
                        break
                    except:
                        pass
    
    # UI елементи
    board_container = ft.Stack([], width=1100, height=790)  # Збільшено висоту на 30 пікселів
    # Контейнер для панелі тейлів поверх сайдбару - достатня ширина для охоплення board + sidebar + spacing
    tile_palette_container = ft.Stack([], width=1400, height=790)
    hints_remaining = 2
    shuffle_remaining = 1
    game_records: List[dict] = []
    current_profile: Dict[str, Optional[Any]] = {"id": None, "username": None, "role": None}
    profile_label = ft.Text("Гравець: (не вхід)", size=14, color=TEXT_COLOR)
    games_label = ft.Text("Ігор: 0", size=12, color="#CCCCCC")
    best_time_s1_label = ft.Text("Кращий час Пасьянс 1: --:--", size=12, color="#CCCCCC")
    best_time_s2_label = ft.Text("Кращий час Пасьянс 2: --:--", size=12, color="#CCCCCC")
    current_session_id: Optional[int] = None
    start_button: Optional[ft.ElevatedButton] = None
    solitaire1_pattern_dropdown: Optional[ft.Dropdown] = None
    selected_solitaire1_pattern: Optional[str] = None
    solitaire2_button: Optional[ft.ElevatedButton] = None
    solitaire2_pattern_dropdown: Optional[ft.Dropdown] = None
    selected_solitaire2_pattern: Optional[str] = None
    duel_button: Optional[ft.ElevatedButton] = None
    duel2_button: Optional[ft.ElevatedButton] = None
    solitaire2_slots: List[Optional[Tile]] = [None, None, None]  # Три слоти для тейлів у Пасьянс 2 (третій може бути заблокований)
    solitaire2_last_move: Optional[Dict[str, Any]] = None  # Останній хід для відміни: {"tile": Tile, "x": int, "y": int, "z": int, "slot_index": int} або None
    solitaire2_pending_removal: bool = False  # Прапор, що вказує, що чекаємо перед видаленням однакових тейлів
    solitaire2_third_slot_unlocked: bool = False  # Чи розблокована третя комірка в поточній грі (Пасьянс 2)
    darken_mode: bool = True  # Глобальний режим затемнення закритих тейлів (за замовчуванням увімкнено)
    selected_solitaire2_pattern: Optional[str] = None  # Вибраний патерн для solitaire2
    selected_solitaire2_pattern: Optional[str] = None  # Вибраний патерн для solitaire2
    timer_text = ft.Text("00:00", size=24, weight=ft.FontWeight.BOLD, color=TEXT_COLOR)
    records_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Дата", size=11)),
            ft.DataColumn(ft.Text("Тривалість", size=11)),
        ],
        rows=[],
        column_spacing=8,
        heading_row_height=30,
        data_row_min_height=35,
        data_row_max_height=35,
        border=None,  # Прибрано border
        divider_thickness=0,  # Прибрано divider
        width=176,  # Зменшено до ширини sidebar (200px) мінус padding (12px * 2 = 24px) = 176px
        horizontal_lines=None,  # Прибрано горизонтальні лінії
        vertical_lines=None,  # Прибрано вертикальні лінії
    )
    reshuffle_prompt_open = False
    reshuffle_dialog: Optional[ft.AlertDialog] = None
    no_moves_dialog_open = False
    no_moves_dialog: Optional[ft.AlertDialog] = None
    is_paused = False
    pause_overlay = ft.Container(
        expand=True,
        bgcolor="#00000088",
        opacity=0,
        animate=ft.Animation(duration=300, curve=ft.AnimationCurve.EASE),
        alignment=ft.alignment.center,
        content=ft.Text("Пауза", size=36, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
        visible=False,
    )
    # Простий напис на полі замість великого вікна
    finish_text_container: Optional[ft.Container] = None
    leaderboard_table = ft.DataTable(
        columns=[
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Гравець", size=12, text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    alignment=ft.alignment.center,
                ),
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Найкращий час", size=12, text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    alignment=ft.alignment.center,
                ),
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Підказки", size=12, text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    alignment=ft.alignment.center,
                ),
            ),
            ft.DataColumn(
                label=ft.Container(
                    content=ft.Text("Тасування", size=12, text_align=ft.TextAlign.CENTER),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    alignment=ft.alignment.center,
                ),
            ),
        ],
        rows=[],
        column_spacing=12,
        heading_row_height=35,
        data_row_min_height=35,
        data_row_max_height=35,
        divider_thickness=1,
        border=ft.border.all(1, "#888888"),
        width=500,
        horizontal_lines=ft.border.BorderSide(1, "#888888"),
        vertical_lines=ft.border.BorderSide(1, "#888888"),
    )
    
    leaderboard_overlay: Optional[ft.Container] = None
    
    def close_leaderboard():
        nonlocal leaderboard_overlay
        if leaderboard_overlay:
            leaderboard_overlay.visible = False
            if leaderboard_overlay in page.overlay:
                page.overlay.remove(leaderboard_overlay)
            page.update()

    def show_leaderboard(e):
        nonlocal leaderboard_overlay
        print(f"DEBUG show_leaderboard: Викликано")
        refresh_leaderboard()
        print(f"DEBUG show_leaderboard: refresh_leaderboard викликано, rows count={len(leaderboard_table.rows)}")
        
        # Створюємо overlay для лідерборду, якщо ще не створено
        if leaderboard_overlay is None:
            leaderboard_overlay = ft.Container(
                expand=True,
                bgcolor="#000000DD",
                alignment=ft.alignment.center,
                content=ft.Container(
                    width=550,
                    height=500,
                    padding=20,
                    bgcolor="#1E1E1E",
                    border_radius=10,
                    content=ft.Column(
                        [
                            ft.Text("Лідери", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                            ft.Container(
                                content=leaderboard_table,
                                height=350,
                            ),
                            ft.Container(
                                content=ft.ElevatedButton("Закрити", on_click=lambda e: close_leaderboard(), width=150),
                                alignment=ft.alignment.center,
                            ),
                        ],
                        spacing=12,
                        tight=True,
                    ),
                ),
            )
            print(f"DEBUG show_leaderboard: leaderboard_overlay створено")
        
        # Додаємо в page.overlay
        if leaderboard_overlay not in page.overlay:
            page.overlay.append(leaderboard_overlay)
            print(f"DEBUG show_leaderboard: leaderboard_overlay додано в page.overlay")
        leaderboard_overlay.visible = True
        print(f"DEBUG show_leaderboard: overlay visible={leaderboard_overlay.visible}, overlay count={len(page.overlay)}")
        page.update()
        print(f"DEBUG show_leaderboard: page.update() викликано")
    start_time = 0.0
    timer_running = False
    elapsed_seconds = 0
    timer_started = False

    class RepeatingTimer:
        def __init__(self, period: float, callback):
            self.period = period
            self.callback = callback
            self._stop_event = threading.Event()
            self._thread: Optional[threading.Thread] = None

        def start(self):
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

        def _run(self):
            while not self._stop_event.wait(self.period):
                self.callback(None)

        def stop(self):
            self._stop_event.set()
            if self._thread:
                self._thread.join(timeout=0.1)

    
    def play_pause_sound(sound_name: str):
        """Відтворює звук (тільки на Windows)"""
        if HAS_WINSOUND and winsound:
            try:
                winsound.PlaySound(sound_name, winsound.SND_ALIAS | winsound.SND_ASYNC)
            except (RuntimeError, AttributeError):
                pass

    def on_timer_tick(e):
        nonlocal elapsed_seconds
        if not timer_running:
            return
        elapsed_seconds = int(time.time() - start_time)
        timer_text.value = format_duration(elapsed_seconds)
        page.update()

    timer_control = RepeatingTimer(1, on_timer_tick)
    
    # Новий простий функціонал входу/реєстрації
    login_username_field = ft.TextField(label="Логін", width=250, autofocus=True)
    login_email_field = ft.TextField(label="E-mail", width=250, visible=False)
    login_password_field = ft.TextField(label="Пароль", password=True, can_reveal_password=True, width=250)
    login_confirm_field = ft.TextField(label="Підтвердження пароля", password=True, can_reveal_password=True, width=250, visible=False)
    auth_error_text = ft.Text("", size=12, color="#FF6B6B")
    auth_overlay_container: Optional[ft.Container] = None
    is_register_mode = False
    
    # Поля для кабінету користувача (зміна пароля)
    cabinet_overlay_container: Optional[ft.Container] = None
    cabinet_old_password_field = ft.TextField(label="Старий пароль", password=True, can_reveal_password=True, width=250)
    cabinet_new_password_field = ft.TextField(label="Новий пароль", password=True, can_reveal_password=True, width=250)
    cabinet_confirm_password_field = ft.TextField(label="Підтвердження пароля", password=True, can_reveal_password=True, width=250)
    cabinet_error_text = ft.Text("", size=12, color="#FF6B6B")
    
    def close_auth_dialog(e=None):
        """Закриває вікно входу/реєстрації"""
        nonlocal auth_overlay_container
        if auth_overlay_container:
            auth_overlay_container.visible = False
            if auth_overlay_container in page.overlay:
                page.overlay.remove(auth_overlay_container)
        page.update()
    
    def handle_successful_login(profile: Dict[str, Any], close_dialog: bool = True):
        """Обробка успішного входу"""
        nonlocal current_profile, game_records, profile_label, auth_overlay_container, hints_remaining, shuffle_remaining
        current_profile["id"] = profile["id"]
        current_profile["username"] = profile["username"]
        current_profile["role"] = profile.get("role", "user")
        profile_label.value = f"Гравець: {profile['username']}"
        game_records = fetch_profile_records(profile["id"])
        refresh_records_table()
        refresh_profile_stats()
        
        # Не завантажуємо hints та shuffles при вході - вони завантажуються при старті гри
        # hints та shuffles в базі - це додаткові куплені, які додаються до базових (2/1) при старті гри
        
        # Оновлюємо sidebar, щоб показати таблицю рекордів
        update_sidebar()
        
        # Приховуємо overlay входу (за замовчуванням)
        if close_dialog:
            close_auth_dialog()
        
        # Ініціалізуємо кнопки режимів
        if start_button is None:
            initialize_start_button()
        if start_button:
            start_button.visible = True
        # Оновлюємо список патернів для solitaire1 перед показом
        if solitaire1_pattern_dropdown:
            refresh_solitaire1_dropdown()
        if solitaire2_button is None:
            initialize_solitaire2_button()
        # Оновлюємо список патернів для solitaire2 перед показом
        if solitaire2_pattern_dropdown:
            refresh_solitaire2_dropdown()
        if solitaire2_button:
            solitaire2_button.visible = True
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = True
        if duel_button is None:
            initialize_duel_button()
        if duel2_button is None:
            initialize_duel2_button()
        if duel_button:
            duel_button.visible = True
        if duel2_button:
            duel2_button.visible = True
        
        refresh_leaderboard()
        refresh_profile_stats()
        update_board()
        page.update()
    
    def handle_login():
        """Обробка входу"""
        username = login_username_field.value.strip()
        password = login_password_field.value or ""
        
        if not username or not password:
            auth_error_text.color = "#FF6B6B"
            auth_error_text.value = "Вкажи логін та пароль"
            page.update()
            return
        
        # Спробувати увійти
        profile = authenticate(username, password)
        if profile:
            # Зберігаємо дані для автоматичного входу
            save_remembered_credentials(username, password)
            handle_successful_login(profile)
        else:
            auth_error_text.color = "#FF6B6B"
            auth_error_text.value = "Невірні логін або пароль"
            page.update()
    
    def handle_register():
        """Обробка реєстрації"""
        username = login_username_field.value.strip()
        email = login_email_field.value.strip()
        password = login_password_field.value or ""
        confirm = login_confirm_field.value or ""
        
        if not username or not email or not password or not confirm:
            auth_error_text.color = "#FF6B6B"
            auth_error_text.value = "Заповни всі поля (логін, e-mail, пароль)"
            page.update()
            return
        
        # Дуже проста валідація e-mail, щоб не захоплюватися регекспами
        if "@" not in email or "." not in email:
            auth_error_text.color = "#FF6B6B"
            auth_error_text.value = "Некоректний e-mail"
            page.update()
            return
        
        if password != confirm:
            auth_error_text.color = "#FF6B6B"
            auth_error_text.value = "Паролі не збігаються"
            page.update()
            return
        
        # Спробувати зареєструватися
        profile = create_profile(username, password, email=email)
        if profile:
            # Зберігаємо дані для автоматичного входу
            save_remembered_credentials(username, password)
            auth_error_text.color = "#4CAF50"
            auth_error_text.value = "Акаунт створено та увійдено"
            page.update()
            # Логінимо користувача, але не закриваємо діалог автоматично
            handle_successful_login(profile, close_dialog=False)
        else:
            auth_error_text.color = "#FF6B6B"
            auth_error_text.value = "Логін вже зайнятий"
            page.update()
    
    def toggle_register_mode(e=None):
        """Перемикання між режимом входу та реєстрації"""
        nonlocal is_register_mode
        is_register_mode = not is_register_mode
        login_confirm_field.visible = is_register_mode
        login_email_field.visible = is_register_mode
        auth_error_text.value = ""
        page.update()
    
    def show_cabinet_dialog(e=None):
        """Показати кабінет користувача для зміни пароля"""
        nonlocal cabinet_overlay_container, cabinet_error_text
        if not current_profile["id"]:
            page.snack_bar = ft.SnackBar(ft.Text("Спочатку увійди в акаунт"), open=True)
            page.update()
            return
        
        # Очищаємо поля
        cabinet_old_password_field.value = ""
        cabinet_new_password_field.value = ""
        cabinet_confirm_password_field.value = ""
        cabinet_error_text.value = ""
        
        def close_cabinet(e=None):
            nonlocal cabinet_overlay_container
            if cabinet_overlay_container:
                cabinet_overlay_container.visible = False
                if cabinet_overlay_container in page.overlay:
                    page.overlay.remove(cabinet_overlay_container)
                page.update()
        
        def handle_change_password(e=None):
            nonlocal cabinet_error_text
            old_pw = cabinet_old_password_field.value or ""
            new_pw = cabinet_new_password_field.value or ""
            confirm_pw = cabinet_confirm_password_field.value or ""
            
            if not old_pw or not new_pw or not confirm_pw:
                cabinet_error_text.value = "Заповни всі поля"
                page.update()
                return
            if new_pw != confirm_pw:
                cabinet_error_text.value = "Нові паролі не співпадають"
                page.update()
                return
            if len(new_pw) < 4:
                cabinet_error_text.value = "Новий пароль має бути мінімум 4 символи"
                page.update()
                return
            
            ok = change_user_password(current_profile["id"], old_pw, new_pw)
            if not ok:
                cabinet_error_text.value = "Старий пароль невірний"
                page.update()
                return
            
            close_cabinet()
            page.snack_bar = ft.SnackBar(ft.Text("Пароль успішно змінено"), open=True)
            page.update()
        
        cabinet_overlay_container = ft.Container(
            expand=True,
            bgcolor="#000000DD",
            alignment=ft.alignment.center,
            content=ft.Container(
                width=320,
                padding=20,
                bgcolor="#1E1E1E",
                border_radius=10,
                content=ft.Column(
                    [
                        ft.Text("Кабінет", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                        cabinet_old_password_field,
                        cabinet_new_password_field,
                        cabinet_confirm_password_field,
                        cabinet_error_text,
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "Зберегти",
                                    width=120,
                                    bgcolor="#4CAF50",
                                    color="#FFFFFF",
                                    on_click=handle_change_password,
                                ),
                                ft.TextButton("Закрити", on_click=close_cabinet),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
        )
        
        if cabinet_overlay_container not in page.overlay:
            page.overlay.append(cabinet_overlay_container)
        page.update()
    
    def show_auth_dialog():
        """Показати overlay входу/реєстрації"""
        nonlocal auth_overlay_container
        print("DEBUG: show_auth_dialog викликано")
        
        # Створюємо overlay контейнер
        auth_overlay_container = ft.Container(
            expand=True,
            bgcolor="#000000DD",
            alignment=ft.alignment.center,
            content=ft.Container(
                width=320,
                padding=20,
                bgcolor="#1E1E1E",
                border_radius=10,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "Вхід / Реєстрація",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color="#FFFFFF",
                                    expand=True,
                                ),
                                ft.IconButton(
                                    icon="close",
                                    icon_color="#FFFFFF",
                                    tooltip="Закрити",
                                    on_click=close_auth_dialog,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        login_username_field,
                        login_email_field,
                        login_password_field,
                        login_confirm_field,
                        auth_error_text,
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "Увійти",
                                    on_click=lambda e: handle_login(),
                                    width=120,
                                ),
                                ft.ElevatedButton(
                                    "Реєстрація",
                                    on_click=lambda e: handle_register(),
                                    width=120,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.TextButton(
                            "Перемкнути на реєстрацію" if not is_register_mode else "Перемкнути на вхід",
                            on_click=toggle_register_mode,
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
        )
        
        # Додаємо в page.overlay
        if auth_overlay_container not in page.overlay:
            page.overlay.append(auth_overlay_container)
        print(f"DEBUG: auth_overlay_container додано в page.overlay, overlay count={len(page.overlay)}")
        page.update()
        print("DEBUG: page.update() викликано після показу overlay")

    def refresh_profile_stats():
        if not current_profile["id"]:
            games_label.value = "Ігор: 0"
            best_time_s1_label.value = "Кращий час Пасьянс 1: --:--"
            best_time_s2_label.value = "Кращий час Пасьянс 2: --:--"
            return
        stats = fetch_profile_stats(current_profile["id"])
        games_label.value = f"Ігор: {stats['games']}"

        # Кращий час для поточного патерну Пасьянс 1 (якщо вибрано)
        pattern_name_s1 = selected_solitaire1_pattern
        if pattern_name_s1:
            best_for_pattern_s1 = fetch_pattern_best_time(
                current_profile["id"], "solitaire1", pattern_name_s1
            )
            if best_for_pattern_s1 is not None:
                best_time_s1_label.value = (
                    f"Пасьянс 1 ({pattern_name_s1}): {format_duration(best_for_pattern_s1)}"
                )
            else:
                best_time_s1_label.value = f"Пасьянс 1 ({pattern_name_s1}): --:--"
        else:
            # Якщо патерн не вибраний, показуємо загальний кращий час по режиму
            if stats.get("best_s1") is not None:
                best_time_s1_label.value = (
                    f"Кращий час Пасьянс 1: {format_duration(stats['best_s1'])}"
                )
            else:
                best_time_s1_label.value = "Кращий час Пасьянс 1: --:--"

        # Кращий час для поточного патерну Пасьянс 2 (якщо вибрано)
        pattern_name_s2 = selected_solitaire2_pattern
        if pattern_name_s2:
            best_for_pattern_s2 = fetch_pattern_best_time(
                current_profile["id"], "solitaire2", pattern_name_s2
            )
            if best_for_pattern_s2 is not None:
                best_time_s2_label.value = (
                    f"Пасьянс 2 ({pattern_name_s2}): {format_duration(best_for_pattern_s2)}"
                )
            else:
                best_time_s2_label.value = f"Пасьянс 2 ({pattern_name_s2}): --:--"
        else:
            if stats.get("best_s2") is not None:
                best_time_s2_label.value = (
                    f"Кращий час Пасьянс 2: {format_duration(stats['best_s2'])}"
                )
            else:
                best_time_s2_label.value = "Кращий час Пасьянс 2: --:--"


    def start_timer(reset: bool = True):
        nonlocal start_time, timer_running, elapsed_seconds, timer_started
        if reset:
            elapsed_seconds = 0
        start_time = time.time() - elapsed_seconds
        timer_text.value = format_duration(elapsed_seconds)
        timer_running = True
        timer_control.start()
        if reset:
            timer_started = True

    def stop_timer():
        nonlocal timer_running
        timer_running = False
        timer_control.stop()

    def update_action_ui():
        # Перевіряємо, чи гра почалася (start_button не видимий = гра активна)
        game_started = not (start_button and start_button.visible)
        
        hint_button.text = f"Підказка ({hints_remaining}/2)"
        shuffle_button.text = f"Тасування ({shuffle_remaining}/1)"
        # Кнопки неактивні, якщо гра не почалася, або закінчена, або на паузі
        hint_button.disabled = not game_started or hints_remaining <= 0 or board.game_over or is_paused
        shuffle_button.disabled = not game_started or shuffle_remaining <= 0 or board.game_over or is_paused
        pause_button.text = "Продовжити" if is_paused else "Пауза"
        pause_button.disabled = not game_started or board.game_over

    def format_timestamp(iso_timestamp: str) -> str:
        """Форматує ISO timestamp в короткий формат"""
        try:
            # Парсимо ISO формат
            dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            # Форматуємо як "22.11.2025 13:56" з меншим розміром
            return dt.strftime("%d.%m.%Y %H:%M")
        except:
            # Якщо не вдалося розпарсити - повертаємо як є, але обрізаємо
            return iso_timestamp[:16] if len(iso_timestamp) > 16 else iso_timestamp
    
    def refresh_records_table():
        records_table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(
                                format_timestamp(record["timestamp"]), 
                                text_align=ft.TextAlign.LEFT,
                                no_wrap=True,
                            ),
                            padding=ft.padding.only(left=2, right=4, top=4, bottom=4),
                            alignment=ft.alignment.center_left,
                        )
                    ),
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(
                                record["time"], 
                                text_align=ft.TextAlign.CENTER,
                                no_wrap=True,
                            ),
                            padding=ft.padding.symmetric(horizontal=6, vertical=4),
                            alignment=ft.alignment.center,
                        )
                    ),
                ],
            )
            for record in game_records
        ]

    def refresh_leaderboard():
        print(f"DEBUG refresh_leaderboard: Початок оновлення таблиці лідерів")
        leaderboard = fetch_leaderboard()
        print(f"DEBUG refresh_leaderboard: Отримано {len(leaderboard)} записів")
        for i, entry in enumerate(leaderboard):
            print(f"DEBUG refresh_leaderboard: entry[{i}] = {entry}")
        print(f"DEBUG refresh_leaderboard: Створюю рядки для таблиці...")
        leaderboard_table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(entry["username"], text_align=ft.TextAlign.CENTER),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            alignment=ft.alignment.center,
                        )
                    ),
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(
                                format_duration(entry["best_time"]) if entry["best_time"] else "--:--",
                                text_align=ft.TextAlign.CENTER
                            ),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            alignment=ft.alignment.center,
                        )
                    ),
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(
                                str(entry.get("hints_used", 0)) if entry.get("best_time") else "--",
                                text_align=ft.TextAlign.CENTER
                            ),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            alignment=ft.alignment.center,
                        )
                    ),
                    ft.DataCell(
                        ft.Container(
                            content=ft.Text(
                                str(entry.get("shuffle_used", 0)) if entry.get("best_time") else "--",
                                text_align=ft.TextAlign.CENTER
                            ),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            alignment=ft.alignment.center,
                        )
                    ),
                ]
            )
            for entry in leaderboard
        ]
        # Додаємо порожній рядок для горизонтальної лінії після останнього користувача
        if leaderboard_table.rows:
            leaderboard_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text("", size=1),
                                height=1,
                                padding=0,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text("", size=1),
                                height=1,
                                padding=0,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text("", size=1),
                                height=1,
                                padding=0,
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text("", size=1),
                                height=1,
                                padding=0,
                            )
                        ),
                    ]
                )
            )
        print(f"DEBUG refresh_leaderboard: Додано {len(leaderboard_table.rows)} рядків у таблицю")
        print(f"DEBUG refresh_leaderboard: Таблиця оновлена, потрібно викликати page.update() для відображення змін")
    def add_record(result_label: str, timestamp: Optional[str] = None):
        nonlocal game_records
        duration = elapsed_seconds if elapsed_seconds else int(time.time() - start_time)
        if current_profile["id"]:
            # Зберігаємо також режим гри та патерн для коректних кращих часів по режимах і патернах
            insert_profile_record(
                current_profile["id"],
                duration,
                timestamp,
                game_mode,
                current_pattern_name,
            )
            game_records = fetch_profile_records(current_profile["id"])
            refresh_profile_stats()
        else:
            if timestamp is None:
                timestamp = datetime.now().isoformat()
            record = {
                "time": format_duration(duration),
                "result": result_label,
                "timestamp": timestamp,
                "duration": duration,
            }
            game_records.insert(0, record)
            if len(game_records) > 5:
                game_records.pop()
        refresh_records_table()

    def start_new_game(e=None, show_notification=True, pattern_name: Optional[str] = None):
        nonlocal board, hints_remaining, shuffle_remaining, timer_started, elapsed_seconds, start_time
        nonlocal current_session_id, solitaire2_slots, finish_text_container, darken_mode
        global game_mode, current_pattern_name
        timer_control.stop()
        # Створюємо нову дошку з поточним game_mode (який вже встановлений) та вибраним патерном
        board = Board(pattern_name=pattern_name)
        # Запам'ятовуємо патерн, з яким запущена гра
        current_pattern_name = pattern_name
        # На початку будь-якої гри завжди 2 підказки і 1 тасування (базові)
        # Додаємо додаткові куплені підказки/тасування з бази даних
        hints_remaining = 2
        shuffle_remaining = 1
        if current_profile["id"] is not None:
            hints_remaining += get_user_hints(current_profile["id"])
            shuffle_remaining += get_user_shuffles(current_profile["id"])
        timer_started = False
        elapsed_seconds = 0
        start_time = 0.0
        timer_text.value = format_duration(0)
        pause_overlay.visible = False
        pause_overlay.opacity = 0
        # Приховуємо напис фінішу при старті нової гри
        if finish_text_container:
            finish_text_container.visible = False
        board_container.opacity = 1
        # Очищаємо слоти для Пасьянс 2
        solitaire2_slots = [None, None, None]
        solitaire2_last_move = None
        solitaire2_pending_removal = False
        # Приховуємо кнопки режимів, бо гра починається
        if start_button:
            start_button.visible = False
        if solitaire1_pattern_dropdown:
            solitaire1_pattern_dropdown.visible = False
        if solitaire2_button:
            solitaire2_button.visible = False
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = False
        if duel_button:
            duel_button.visible = False
        if duel2_button:
            duel2_button.visible = False
        update_action_ui()
        update_board()
        if show_notification:
            page.snack_bar = ft.SnackBar(ft.Text("Нова гра розпочата"), open=True)
        refresh_leaderboard()

    def finalize_game(result_label: str):
        nonlocal current_session_id, duel2_button
        if board.game_over:
            return
        stop_timer()
        board.game_over = True
        record_duration = elapsed_seconds if elapsed_seconds else int(time.time() - start_time)
        durations = [r["duration"] for r in game_records if isinstance(r.get("duration"), (int, float))]
        previous_best = min(durations) if durations else None
        new_record = previous_best is None or record_duration < previous_best
        
        # Спочатку обчислюємо підказки і тасування
        hints_used = HINT_LIMIT - hints_remaining
        shuffle_used = SHUFFLE_LIMIT - shuffle_remaining
        if hints_used < 0:
            hints_used = 0
        if shuffle_used < 0:
            shuffle_used = 0
        
        # Спочатку завершуємо сесію, щоб end_time був встановлений
        session_end_time = None
        session_id_to_end = current_session_id
        if session_id_to_end:
            session_end_time = end_session(session_id_to_end, result_label, hints_used, shuffle_used)
            print(f"DEBUG finalize_game: Завершено сесію {session_id_to_end}, end_time={session_end_time}, hints={hints_used}, shuffle={shuffle_used}")
            current_session_id = None
        else:
            print(f"DEBUG finalize_game: ПОМИЛКА! current_session_id is None, дані про підказки та тасування не будуть збережені!")
        
        # Потім додаємо запис, використовуючи той самий timestamp
        add_record(result_label, session_end_time)
        print(f"DEBUG finalize_game: Додано запис з timestamp={session_end_time}")
        refresh_leaderboard()
        
        # Нараховуємо coins за результати гри (тільки для пасьянс-1 і пасьянс-2, не дуелі)
        coins_to_add = 0
        if current_profile["id"] is not None and game_mode in ["solitaire1", "solitaire2"]:
            if result_label == "Виграш":
                if new_record:
                    # Побив свій рекорд → +5 coins
                    coins_to_add = 5
                else:
                    # Дійшов до фінішу, але не побив рекорд → +1 coin
                    coins_to_add = 1
            elif result_label == "Немає ходів":
                # Якщо немає можливих ходів і немає тасувань → 0 coins
                if shuffle_remaining <= 0:
                    coins_to_add = 0
                # Якщо є тасування, але користувач не використав - все одно 0 coins (немає ходів)
                else:
                    coins_to_add = 0
            
            # Оновлюємо coins в базі даних
            if coins_to_add > 0:
                current_coins = get_user_coins(current_profile["id"])
                update_user_coins(current_profile["id"], current_coins + coins_to_add)
                print(f"DEBUG finalize_game: Нараховано {coins_to_add} coins. Загалом: {current_coins + coins_to_add}")
                # Оновлюємо відображення coins в sidebar
                update_sidebar()
        
        # Після завершення гри показуємо кнопки режимів
        if start_button:
            start_button.visible = True
        if solitaire1_pattern_dropdown:
            solitaire1_pattern_dropdown.visible = True
        if solitaire2_button:
            solitaire2_button.visible = True
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = True
        if duel_button:
            duel_button.visible = True
        if duel2_button:
            duel2_button.visible = True
        
        # Створюємо простий напис на полі замість великого вікна
        nonlocal finish_text_container
        
        # Формуємо список елементів для відображення
        finish_content = [
            ft.Text("Фініш", size=24, weight=ft.FontWeight.BOLD, color=TEXT_COLOR, text_align=ft.TextAlign.CENTER),
            ft.Text(f"Час: {format_duration(record_duration)}", size=18, color=TEXT_COLOR, text_align=ft.TextAlign.CENTER),
        ]
        
        # Додаємо "Новий рекорд!" якщо є
        if new_record:
            finish_content.append(
                ft.Text(
                    "Новий рекорд!",
                    size=16,
                    color=HINT_COLOR,
                    text_align=ft.TextAlign.CENTER,
                )
            )
        
        # Додаємо інформацію про coins (тільки для пасьянс-1 і пасьянс-2)
        if current_profile["id"] is not None and game_mode in ["solitaire1", "solitaire2"]:
            if coins_to_add > 0:
                finish_content.append(
                    ft.Text(
                        f"+{coins_to_add} coins",
                        size=16,
                        color="#FFD700",  # Золотий колір для coins
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                    )
                )
            elif result_label == "Немає ходів":
                # Якщо немає ходів, показуємо "+0 coins"
                finish_content.append(
                    ft.Text(
                        "+0 coins",
                        size=16,
                        color="#999999",
                        text_align=ft.TextAlign.CENTER,
                    )
                )
        
        finish_text_container = ft.Container(
            content=ft.Column(
                finish_content,
                spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            left=400,  # Центруємо на полі (приблизно)
            top=300,
            width=300,
            height=150,
            bgcolor="#222222CC",  # Напівпрозорий темний фон
            border_radius=10,
            border=ft.border.all(2, TEXT_COLOR),
            alignment=ft.alignment.center,
        )
        page.snack_bar = ft.SnackBar(ft.Text(f"Гра завершена: {result_label}"), open=True)
        update_action_ui()
        update_board()
        page.update()

    def request_hint(e):
        nonlocal hints_remaining
        # Перевіряємо, чи гра почалася
        if start_button and start_button.visible:
            return
        if is_paused:
            return
        if hints_remaining <= 0 or board.game_over:
            return
        board.clear_highlights()
        if board.selected_tile:
            board.selected_tile.selected = False
            board.selected_tile = None
        pair = board.find_hint_pair()
        if not pair:
            page.snack_bar = ft.SnackBar(ft.Text("Ходів для підказки більше немає"), open=True)
            page.update()
            return
        hints_remaining -= 1
        # Оновлюємо куплені підказки в базі даних, якщо користувач увійшов
        # Базові підказки = 2, тому куплені = hints_remaining - 2 (але не менше 0)
        if current_profile["id"] is not None:
            bought_hints = max(0, hints_remaining - 2)
            update_user_hints(current_profile["id"], bought_hints)
        tile1, tile2 = pair
        tile1.highlighted = True
        tile2.highlighted = True
        update_action_ui()
        update_board()

    def request_shuffle(e):
        nonlocal shuffle_remaining, solitaire2_slots, solitaire2_last_move
        # Перевіряємо, чи гра почалася
        if start_button and start_button.visible:
            return
        if is_paused:
            return
        if shuffle_remaining <= 0 or board.game_over:
            return
        shuffle_remaining -= 1
        # Оновлюємо куплені тасування в базі даних, якщо користувач увійшов
        # Базове тасування = 1, тому куплені = shuffle_remaining - 1 (але не менше 0)
        if current_profile["id"] is not None:
            bought_shuffles = max(0, shuffle_remaining - 1)
            update_user_shuffles(current_profile["id"], bought_shuffles)

        # Для Пасьянсу-2: перед тасуванням повертаємо всі тейли з комірок назад на поле
        if game_mode == "solitaire2":
            # Скидаємо можливість undo для останнього ходу, бо розклад зміниться
            solitaire2_last_move = None
            for i in range(len(solitaire2_slots)):
                slot_tile = solitaire2_slots[i]
                if slot_tile is not None:
                    # Повертаємо тейл на поле: просто робимо його не видаленим
                    # (його координати на полі збережені, ми лише ховали його через removed=True)
                    slot_tile.removed = False
                    slot_tile.selected = False
                    slot_tile.highlighted = False
                    solitaire2_slots[i] = None

        board.clear_highlights()
        board.reshuffle_remaining_tiles()
        update_action_ui()
        update_board()

    def close_reshuffle_dialog():
        nonlocal reshuffle_prompt_open
        reshuffle_prompt_open = False
        if reshuffle_dialog:
            reshuffle_dialog.open = False
        page.dialog = None

    def handle_reshuffle(e):
        """Перетасовує плитки, коли гравець погоджується"""
        close_reshuffle_dialog()
        request_shuffle(e)

    def handle_end_game(e):
        """Закінчує гру, якщо гравцю не потрібно перетасовувати"""
        close_reshuffle_dialog()
        finalize_game("Немає ходів")

    def toggle_pause(e):
        nonlocal is_paused
        # Перевіряємо, чи гра почалася
        if start_button and start_button.visible:
            return
        if board.game_over:
            return
        is_paused = not is_paused
        pause_overlay.visible = True
        if is_paused:
            pause_overlay.opacity = 1
            board_container.opacity = 0
            stop_timer()
            play_pause_sound("SystemHand")
        else:
            pause_overlay.opacity = 0
            board_container.opacity = 1
            start_timer(reset=False)
            play_pause_sound("SystemExclamation")
            pause_overlay.visible = False
        update_action_ui()
        update_board()
        page.update()

    reshuffle_dialog = ft.AlertDialog(
        title=ft.Text("Немає ходів"),
        content=ft.Text("Хочеш перетасувати плитки чи закінчити гру?"),
        actions=[
            ft.TextButton("Перетасувати", on_click=handle_reshuffle),
            ft.TextButton("Завершити", on_click=handle_end_game),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def show_reshuffle_prompt():
        nonlocal reshuffle_prompt_open
        reshuffle_prompt_open = True
        reshuffle_dialog.open = True
        page.dialog = reshuffle_dialog
        page.update()

    def close_no_moves_dialog():
        """Закриває діалог про відсутність ходів"""
        nonlocal no_moves_dialog_open
        no_moves_dialog_open = False
        if no_moves_dialog:
            no_moves_dialog.open = False
        page.dialog = None
        page.update()

    def handle_end_game_no_moves(e):
        """Завершує гру, якщо гравцю не потрібно відкривати третю комірку"""
        close_no_moves_dialog()
        finalize_game("Немає ходів")

    def handle_continue_game(e):
        """Продовжує гру, дозволяючи відкрити третю комірку"""
        close_no_moves_dialog()

    no_moves_dialog = ft.AlertDialog(
        title=ft.Text("Немає ходів"),
        content=ft.Text("Або відкрийте третю комірку, або ходів не має. Завершити гру?"),
        actions=[
            ft.TextButton("Ні", on_click=handle_continue_game),
            ft.TextButton("Так", on_click=handle_end_game_no_moves),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def check_solitaire2_no_moves() -> bool:
        """Перевіряє, чи немає можливих ходів у solitaire2 після undo"""
        # Визначаємо кількість доступних комірок (поки що 2, третя закрита)
        available_slots_count = 2  # Третя комірка поки закрита
        
        # Перевіряємо, чи всі доступні комірки зайняті
        occupied_slots = []
        for i in range(available_slots_count):
            if solitaire2_slots[i] is not None:
                occupied_slots.append(i)
        
        # Отримуємо доступні тейли на полі
        available_tiles = [tile for tile in board.tiles if not tile.removed and board.is_tile_available(tile)]
        
        # Якщо всі комірки зайняті
        if len(occupied_slots) == available_slots_count:
            # Перевіряємо, чи тейли в комірках різні
            if solitaire2_slots[0].tile_type == solitaire2_slots[1].tile_type:
                return False  # Тейли однакові, вони будуть видалені
            
            # Обидві комірки зайняті різними тейлами
            # Перевіряємо, чи є на полі доступний тейл, який відповідає тейлу в комірці
            for slot_index in occupied_slots:
                slot_tile = solitaire2_slots[slot_index]
                slot_tile_type = slot_tile.tile_type
                
                # Перевіряємо, чи є на полі доступний тейл того ж типу
                for field_tile in available_tiles:
                    if field_tile.tile_type == slot_tile_type:
                        # Знайдено відповідний тейл на полі - можна зробити хід
                        return False
            
            # Не знайдено відповідних тейлів на полі для жодного тейла з комірок
            # Перевіряємо, чи є взагалі можливі пари на полі (між тейлами на полі)
            if len(available_tiles) >= 2:
                for i, tile1 in enumerate(available_tiles):
                    for tile2 in available_tiles[i + 1:]:
                        if tile1.tile_type == tile2.tile_type and board.can_connect(tile1, tile2):
                            # Знайдено можливу пару на полі - можна продовжити гру
                            return False
            
            # Не знайдено можливих пар - показуємо діалог
            return True
        
        # Якщо одна комірка зайнята (або обидві вільні)
        # Перевіряємо, чи є на полі однакові відкрити тейли
        # Якщо немає - то навіть якщо заповнити другу комірку, пар не буде
        if len(available_tiles) >= 2:
            # Перевіряємо, чи є хоча б одна пара однакових відкритих тейлів на полі
            for i, tile1 in enumerate(available_tiles):
                for tile2 in available_tiles[i + 1:]:
                    if tile1.tile_type == tile2.tile_type and board.can_connect(tile1, tile2):
                        # Знайдено можливу пару на полі - можна продовжити гру
                        return False
        
        # Якщо одна комірка зайнята і на полі немає однакових відкритих тейлів
        # Перевіряємо, чи можна використати тейл з комірки
        if len(occupied_slots) == 1:
            slot_tile = solitaire2_slots[occupied_slots[0]]
            slot_tile_type = slot_tile.tile_type
            
            # Перевіряємо, чи є на полі доступний тейл того ж типу
            for field_tile in available_tiles:
                if field_tile.tile_type == slot_tile_type:
                    # Знайдено відповідний тейл на полі - можна зробити хід
                    return False
        
        # Не знайдено можливих пар - показуємо діалог
        return True

    def show_no_moves_prompt():
        """Показує діалог про відсутність ходів"""
        nonlocal no_moves_dialog_open
        if no_moves_dialog_open:
            return  # Діалог вже відкритий
        no_moves_dialog_open = True
        no_moves_dialog.open = True
        page.dialog = no_moves_dialog
        page.update()

    def check_game_state():
        """Перевіряє стан гри (виграш, немає ходів)"""
        if board.game_over:
            return
        if is_paused:
            return
        if board.is_game_won():
            finalize_game("Виграш")
            return
        if reshuffle_prompt_open:
            return
        if no_moves_dialog_open:
            return
        # Для solitaire2 перевіряємо спеціальну логіку
        # ТИМЧАСОВО ВИМКНЕНО: поки не показуємо діалог про завершення гри
        # if game_mode == "solitaire2":
        #     if check_solitaire2_no_moves():
        #         show_no_moves_prompt()
        else:
            # Для інших режимів - стандартна перевірка
            if not board.has_possible_moves():
                show_reshuffle_prompt()
        # Приховуємо напис фінішу
        nonlocal finish_text_container
        if finish_text_container:
            finish_text_container.visible = False

    refresh_records_table()

    hint_button = ft.ElevatedButton(
        "Підказка (2/2)",
        icon=ft.Icon(name="lightbulb_outline", color=HINT_COLOR),
        on_click=request_hint,
        width=180,
    )
    shuffle_button = ft.ElevatedButton(
        "Тасування (1/1)",
        icon=ft.Icon(name="shuffle", color="#FFFFFF"),
        on_click=request_shuffle,
        width=180,
    )
    pause_button = ft.ElevatedButton(
        "Пауза",
        on_click=toggle_pause,
        width=180,
    )
    leaderboard_button = ft.ElevatedButton(
        "Лідери",
        width=180,
        on_click=show_leaderboard,
    )
    
    # АДМІНСЬКА КНОПКА ДЛЯ ТЕСТУВАННЯ - видаляє 10 плиток
    def admin_remove_10_tiles(e):
        """Адмінська функція для швидкого тестування - видаляє 10 доступних плиток"""
        print("DEBUG admin_remove_10_tiles: Кнопка натиснута")
        if board.game_over:
            print("DEBUG admin_remove_10_tiles: Гра вже завершена")
            return
        if start_button and start_button.visible:
            print("DEBUG admin_remove_10_tiles: Гра не почалася")
            page.snack_bar = ft.SnackBar(ft.Text("Спочатку почни гру"), open=True)
            page.update()
            return
        
        # Знаходимо всі доступні плитки
        available_tiles = []
        for tile in board.tiles:
            if not tile.removed and board.is_tile_available(tile):
                available_tiles.append(tile)
        
        print(f"DEBUG admin_remove_10_tiles: Знайдено {len(available_tiles)} доступних плиток")
        
        if not available_tiles:
            print("DEBUG admin_remove_10_tiles: Немає доступних плиток")
            page.snack_bar = ft.SnackBar(ft.Text("Немає доступних плиток"), open=True)
            page.update()
            return
        
        # Просто видаляємо перші 10 доступних плиток (без перевірки пар)
        removed_count = 0
        for tile in available_tiles[:10]:
            if not tile.removed:
                tile.removed = True
                removed_count += 1
        
        print(f"DEBUG admin_remove_10_tiles: Видалено {removed_count} плиток")
        
        update_board()
        check_game_state()
        page.snack_bar = ft.SnackBar(ft.Text(f"Видалено {removed_count} плиток (адмін)"), open=True)
        page.update()
        print("DEBUG admin_remove_10_tiles: Оновлення завершено")
    
    admin_button = ft.ElevatedButton(
        "-10",
        width=180,
        bgcolor="#FF4444",
        color="#FFFFFF",
        on_click=admin_remove_10_tiles,
    )
    
    # Кнопка Support з модальним вікном
    support_overlay: Optional[ft.Container] = None
    
    def close_support():
        """Закриває модальне вікно підтримки"""
        nonlocal support_overlay
        if support_overlay:
            support_overlay.visible = False
            if support_overlay in page.overlay:
                page.overlay.remove(support_overlay)
            page.update()
    
    def show_support(e):
        """Показує модальне вікно з контактною інформацією"""
        nonlocal support_overlay
        if support_overlay is None:
            support_overlay = ft.Container(
                expand=True,
                bgcolor="#000000DD",
                alignment=ft.alignment.center,
                content=ft.Container(
                    width=450,
                    height=250,
                    padding=20,
                    bgcolor="#1E1E1E",
                    border_radius=10,
                    content=ft.Column(
                        [
                            ft.Text("Підтримка", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                            ft.Divider(height=10),
                            ft.Text("Якщо у вас виникли питання або пропозиції, зв'яжіться з нами:", size=14, color="#FFFFFF"),
                            ft.Divider(height=10),
                            ft.Row(
                                [
                                    ft.Text("Email: ", size=14, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                                    ft.Text("music319@gmail.com", size=14, color="#4CAF50", selectable=True),
                                ],
                                spacing=8,
                            ),
                            ft.Container(height=20),
                            ft.ElevatedButton("Закрити", on_click=lambda e: close_support(), width=150),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                ),
                visible=False,
            )
        
        if support_overlay not in page.overlay:
            page.overlay.append(support_overlay)
        support_overlay.visible = True
        page.update()
    
    support_button = ft.ElevatedButton(
        "Support",
        width=180,
        bgcolor="#2196F3",
        color="#FFFFFF",
        on_click=show_support,
    )
    
    # Overlay для діалогу підтвердження завершення гри
    end_game_overlay: Optional[ft.Container] = None
    
    def close_end_game_dialog():
        """Закриває діалог підтвердження завершення гри"""
        nonlocal end_game_overlay
        if end_game_overlay:
            end_game_overlay.visible = False
            if end_game_overlay in page.overlay:
                page.overlay.remove(end_game_overlay)
            page.update()
    
    def confirm_end_game_and_show_modes(e):
        """Підтверджує завершення гри і показує режими"""
        nonlocal current_session_id, board, hints_remaining, shuffle_remaining
        print(f"DEBUG confirm_end_game_and_show_modes: Викликано")
        close_end_game_dialog()
        
        # Завершуємо гру як "Перервано"
        if board and not board.game_over and current_session_id is not None:
            print(f"DEBUG confirm_end_game_and_show_modes: Завершую гру")
            # Обчислюємо підказки і тасування
            HINT_LIMIT = 2
            SHUFFLE_LIMIT = 1
            hints_used = HINT_LIMIT - hints_remaining
            shuffle_used = SHUFFLE_LIMIT - shuffle_remaining
            if hints_used < 0:
                hints_used = 0
            if shuffle_used < 0:
                shuffle_used = 0
            
            # Завершуємо сесію
            session_id_to_end = current_session_id
            if session_id_to_end:
                end_session(session_id_to_end, "Перервано", hints_used, shuffle_used)
                current_session_id = None
            
            # Встановлюємо гра завершеною
            board.game_over = True
            stop_timer()
        
        # Показуємо режими
        show_modes_page_internal()
    
    def show_modes_page_internal():
        """Внутрішня функція для показу сторінки вибору режимів"""
        nonlocal start_button, solitaire2_button, duel_button, duel2_button, board, current_session_id, pattern_constructor_mode, finish_text_container
        print(f"DEBUG show_modes_page_internal: Викликано")
        pattern_constructor_mode = False  # Скидаємо режим конструктора при показі режимів
        # Приховуємо напис фінішу при виборі режимів
        if finish_text_container:
            finish_text_container.visible = False
        
        # Ініціалізуємо кнопки, якщо вони ще не ініціалізовані
        if start_button is None:
            print(f"DEBUG show_modes_page_internal: Ініціалізую start_button")
            initialize_start_button()
        if solitaire2_button is None:
            print(f"DEBUG show_modes_page_internal: Ініціалізую solitaire2_button")
            initialize_solitaire2_button()
        if duel_button is None:
            print(f"DEBUG show_modes_page_internal: Ініціалізую duel_button")
            initialize_duel_button()
        if duel2_button is None:
            print(f"DEBUG show_modes_page_internal: Ініціалізую duel2_button")
            initialize_duel2_button()
        
        # Якщо гра завершена, закриваємо сесію
        if board and board.game_over and current_session_id is not None:
            print(f"DEBUG show_modes_page_internal: Гра завершена, закриваю сесію")
            current_session_id = None
        
        # Перевіряємо, чи користувач увійшов
        if current_profile["id"] is None:
            print(f"DEBUG show_modes_page_internal: Користувач не увійшов")
            page.snack_bar = ft.SnackBar(ft.Text("Спочатку увійди в систему"), open=True)
            page.update()
            return
        
        # Показуємо кнопки режимів
        if start_button:
            start_button.visible = True
            print(f"DEBUG show_modes_page_internal: start_button.visible встановлено в True")
        # Оновлюємо список патернів для solitaire1 перед показом
        if solitaire1_pattern_dropdown:
            refresh_solitaire1_dropdown()
        # Оновлюємо список патернів для solitaire2 перед показом
        if solitaire2_pattern_dropdown:
            refresh_solitaire2_dropdown()
        if solitaire2_button:
            solitaire2_button.visible = True
            print(f"DEBUG show_modes_page_internal: solitaire2_button.visible встановлено в True")
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = True
        if duel_button:
            duel_button.visible = True
            print(f"DEBUG show_modes_page_internal: duel_button.visible встановлено в True")
        if duel2_button:
            duel2_button.visible = True
            print(f"DEBUG show_modes_page_internal: duel2_button.visible встановлено в True")
        
        # Оновлюємо дошку, щоб показати рамочки з кнопками
        update_board()
        page.update()
        print(f"DEBUG show_modes_page_internal: update_board() та page.update() викликано")
    
    # Конструктор патернів
    pattern_constructor_mode = False
    constructor_pattern: List[List[List[bool]]] = []  # [z][y][x] -> True = місце для тейла, False = порожнє
    constructor_current_layer = 0  # Поточний активний шар
    constructor_cols = 20  # Як у пасьянс-1
    constructor_rows = 10  # Як у пасьянс-1
    constructor_loaded_pattern_name: Optional[str] = None  # Назва завантаженого патерну для редагування
    constructor_game_mode: str = "solitaire1"  # Тип пасьянсу для якого створюється патерн (solitaire1/solitaire2)
    
    def initialize_pattern_constructor():
        """Ініціалізує конструктор патернів з порожнім полем"""
        nonlocal constructor_pattern, constructor_current_layer, sidebar_slots_area, constructor_loaded_pattern_name, constructor_game_mode
        # Створюємо порожній патерн з одним шаром: [z][y][x] -> False (немає тейла)
        constructor_pattern = [
            [[False for _ in range(constructor_cols)] for _ in range(constructor_rows)]
        ]
        constructor_current_layer = 0  # Починаємо з першого шару
        constructor_loaded_pattern_name = None  # Очищаємо назву завантаженого патерну
        constructor_game_mode = "solitaire1"  # Скидаємо тип пасьянсу на solitaire1
        # Очищаємо комірки в прозорій зоні сайдбару для конструктора
        if sidebar_slots_area.content is None or not isinstance(sidebar_slots_area.content, ft.Stack):
            sidebar_slots_area.content = ft.Stack([])
        else:
            sidebar_slots_area.content.controls.clear()
        print(f"DEBUG initialize_pattern_constructor: Створено порожній патерн 1x{constructor_rows}x{constructor_cols}")
    
    def open_pattern_constructor():
        """Відкриває конструктор патернів"""
        nonlocal pattern_constructor_mode, board, start_button, solitaire2_button, duel_button, duel2_button, finish_text_container
        global game_mode
        print(f"DEBUG open_pattern_constructor: Відкриваю конструктор")
        
        # Перевіряємо, чи гра активна
        is_game_active = board and not board.game_over and current_session_id is not None
        if is_game_active:
            # Показуємо діалог підтвердження
            if end_game_overlay:
                end_game_overlay.visible = True
                if end_game_overlay not in page.overlay:
                    page.overlay.append(end_game_overlay)
                page.update()
            return
        
        # Приховуємо кнопки режимів
        if start_button:
            start_button.visible = False
        if solitaire1_pattern_dropdown:
            solitaire1_pattern_dropdown.visible = False
        if solitaire2_button:
            solitaire2_button.visible = False
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = False
        if duel_button:
            duel_button.visible = False
        if duel2_button:
            duel2_button.visible = False
        # При переході в конструктор ховаємо та очищаємо вікно фінішу, якщо воно було
        if finish_text_container:
            finish_text_container.visible = False
            finish_text_container = None
        
        # Встановлюємо режим конструктора
        pattern_constructor_mode = True
        game_mode = "pattern_constructor"
        initialize_pattern_constructor()
        print(f"DEBUG open_pattern_constructor: pattern_constructor_mode={pattern_constructor_mode}, game_mode={game_mode}")
        update_board()
        page.update()
        print(f"DEBUG open_pattern_constructor: update_board() та page.update() викликано")
    
    def close_pattern_constructor():
        """Закриває конструктор патернів"""
        nonlocal pattern_constructor_mode
        global game_mode
        pattern_constructor_mode = False
        game_mode = "solitaire1"
        update_board()
        page.update()
    
    def render_pattern_constructor():
        """Відображає конструктор патернів"""
        nonlocal constructor_pattern, constructor_game_mode
        
        # Очищаємо контейнер
        board_container.controls.clear()
        
        # Випадаюче меню для вибору типу пасьянсу (справа від патерну, в правому верхньому куті)
        def on_game_mode_changed(e):
            nonlocal constructor_game_mode
            constructor_game_mode = e.control.value
            print(f"DEBUG render_pattern_constructor: Змінено тип пасьянсу на {constructor_game_mode}")
        
        game_mode_dropdown = ft.Dropdown(
            label="Тип пасьянсу",
            width=200,
            options=[
                ft.dropdown.Option(text="Пасьянс 1", key="solitaire1"),
                ft.dropdown.Option(text="Пасьянс 2", key="solitaire2"),
            ],
            value=constructor_game_mode,
            on_change=on_game_mode_changed,
        )
        
        # Розміщуємо меню в правому верхньому куті (справа від сітки патерну)
        sidebar_width = 260
        spacing = 12
        # Позиція: справа від сітки, вгорі
        # Сітка починається з grid_start_x=10, має ширину available_width
        grid_start_x = 10
        available_width = board_container.width - sidebar_width - spacing - 20
        dropdown_x = grid_start_x + available_width + 20  # Справа від сітки з відступом 20px
        dropdown_y = 10  # Вгорі
        
        board_container.controls.append(
            ft.Container(
                content=game_mode_dropdown,
                left=dropdown_x,
                top=dropdown_y,
            )
        )
        
        # Відображаємо поле конструктора - одне велике поле з сіткою 20x10
        # Панель тейлів більше не відображається, тому поле займає більшу частину простору
        grid_start_x = 10
        grid_start_y = 10  # Піднято до верхнього краю
        
        # Ширина sidebar = 260px, spacing = 12px
        sidebar_width = 260
        spacing = 12
        available_width = board_container.width - sidebar_width - spacing - 20  # 20px відступ (без панелі тейлів)
        available_height = board_container.height - grid_start_y - 20  # 20px відступ знизу
        
        # Розраховуємо розмір клітинок, щоб поміститися всі 20x10
        # Зберігаємо пропорції реальних тейлів (50x70, тобто співвідношення 1:1.4)
        tile_ratio = TILE_HEIGHT / TILE_WIDTH  # 70/50 = 1.4
        
        # Спочатку розраховуємо ширину клітинки на основі доступної ширини
        grid_cell_size = available_width // constructor_cols  # Розмір клітинки для 20 колонок
        
        # Потім розраховуємо висоту з урахуванням пропорцій тейлів
        grid_cell_height = int(grid_cell_size * tile_ratio)  # Висота зберігає пропорції тейлів
        
        # Перевіряємо, чи поміщаються всі рядки з такою висотою
        total_height_needed = grid_cell_height * constructor_rows
        if total_height_needed > available_height:
            # Якщо не поміщається, зменшуємо висоту пропорційно
            grid_cell_height = available_height // constructor_rows
            # І перераховуємо ширину, щоб зберегти пропорції
            grid_cell_size = int(grid_cell_height / tile_ratio)
        
        # Використовуємо всі 20 колонок і 10 рядків
        max_cols = constructor_cols  # 20 колонок
        max_rows = constructor_rows  # 10 рядків
        
        # Переконаємося, що поточний шар існує
        if constructor_current_layer >= len(constructor_pattern):
            # Якщо шар не існує, створюємо його
            while len(constructor_pattern) <= constructor_current_layer:
                constructor_pattern.append([[False for _ in range(constructor_cols)] for _ in range(constructor_rows)])
        
        # Спочатку малюємо поточний активний шар (клітинки з можливістю кліку)
        z = constructor_current_layer
        for y in range(max_rows):
            for x in range(max_cols):
                cell_x = grid_start_x + x * grid_cell_size
                cell_y = grid_start_y + y * grid_cell_height
                
                # Перевіряємо, чи позначено місце для тейла
                is_marked = False
                if z < len(constructor_pattern) and y < len(constructor_pattern[z]) and x < len(constructor_pattern[z][y]):
                    is_marked = constructor_pattern[z][y][x]
                
                # Створюємо клітинку сітки (завжди видима для орієнтації)
                cell_bgcolor = "#3A3A3A" if (x + y) % 2 == 0 else "#333333"
                if is_marked:
                    cell_bgcolor = "#5A5A5A"  # Місце позначено для тейла
                
                cell = ft.Container(
                    width=grid_cell_size - 1,
                    height=grid_cell_height - 1,
                    left=cell_x,
                    top=cell_y,
                    bgcolor=cell_bgcolor,
                    border=ft.border.all(1, "#555555"),
                    on_click=lambda e, z_coord=z, y_coord=y, x_coord=x: constructor_cell_clicked(z_coord, y_coord, x_coord),
                )
                board_container.controls.append(cell)
                
                # Якщо місце позначено, показуємо індикатор (невеликий маркер)
                if is_marked:
                    marker = ft.Container(
                        width=20,
                        height=20,
                        left=cell_x + (grid_cell_size - 20) // 2,
                        top=cell_y + (grid_cell_height - 20) // 2,
                        bgcolor="#4CAF50",  # Зелений маркер
                        border_radius=10,
                        border=ft.border.all(2, "#FFFFFF"),
                    )
                    board_container.controls.append(marker)
        
        # Тепер малюємо попередні шари (z < constructor_current_layer) тільки контуром ПОВЕРХ поточного
        # Це гарантує, що контури будуть видимі, але не блокуватимуть кліки (немає on_click)
        for z in range(constructor_current_layer):
            if z >= len(constructor_pattern):
                continue
                
            for y in range(max_rows):
                for x in range(max_cols):
                    cell_x = grid_start_x + x * grid_cell_size
                    cell_y = grid_start_y + y * grid_cell_height
                    
                    # Перевіряємо, чи позначено місце для тейла
                    is_marked = False
                    if y < len(constructor_pattern[z]) and x < len(constructor_pattern[z][y]):
                        is_marked = constructor_pattern[z][y][x]
                    
                    # Показуємо тільки позначені місця попередніх шарів тільки контуром (без заливки)
                    # Малюємо контури ПОВЕРХ клітинок поточного шару, але тільки по краях, щоб не блокувати кліки в центрі
                    if is_marked:
                        # Контур клітинки з позначкою - тільки по краях, щоб не перекривати центр
                        # Робимо контур меншим, щоб залишити центр вільною для кліків
                        # Верхній край
                        top_border = ft.Container(
                            width=grid_cell_size - 8,
                            height=3,
                            left=cell_x + 4,
                            top=cell_y + 1,
                            bgcolor="#AAAAAA",  # Світло-сірий колір для помітності
                        )
                        board_container.controls.append(top_border)
                        
                        # Нижній край
                        bottom_border = ft.Container(
                            width=grid_cell_size - 8,
                            height=3,
                            left=cell_x + 4,
                            top=cell_y + grid_cell_height - 4,
                            bgcolor="#AAAAAA",
                        )
                        board_container.controls.append(bottom_border)
                        
                        # Лівий край
                        left_border = ft.Container(
                            width=3,
                            height=grid_cell_height - 8,
                            left=cell_x + 1,
                            top=cell_y + 4,
                            bgcolor="#AAAAAA",
                        )
                        board_container.controls.append(left_border)
                        
                        # Правий край
                        right_border = ft.Container(
                            width=3,
                            height=grid_cell_height - 8,
                            left=cell_x + grid_cell_size - 4,
                            top=cell_y + 4,
                            bgcolor="#AAAAAA",
                        )
                        board_container.controls.append(right_border)
                        
                        # Контур маркера - маленький кружечок по краю, щоб не перекривати центр
                        marker = ft.Container(
                            width=12,
                            height=12,
                            left=cell_x + (grid_cell_size - 12) // 2,
                            top=cell_y + 2,  # Розміщуємо зверху, щоб не перекривати центр
                            bgcolor=None,  # Без заливки
                            border_radius=6,
                            border=ft.border.all(2, "#AAAAAA"),  # Тонка світло-сіра рамка
                        )
                        board_container.controls.append(marker)
        
        # Панель керування шарами (червоне поле знизу)
        render_constructor_controls()
    
    def render_constructor_controls():
        """Відображає панель керування конструктором (кнопки для шарів)"""
        nonlocal constructor_current_layer, constructor_pattern, constructor_loaded_pattern_name, constructor_game_mode
        
        # Розміщуємо панель одразу під сіткою
        # Розраховуємо позицію на основі розмірів сітки
        grid_start_x = 10
        grid_start_y = 10
        sidebar_width = 260
        spacing = 12
        available_width = board_container.width - sidebar_width - spacing - 20
        available_height = board_container.height - grid_start_y - 20
        tile_ratio = TILE_HEIGHT / TILE_WIDTH
        grid_cell_size = available_width // constructor_cols
        grid_cell_height = int(grid_cell_size * tile_ratio)
        if grid_cell_height * constructor_rows > available_height:
            grid_cell_height = available_height // constructor_rows
            grid_cell_size = int(grid_cell_height / tile_ratio)
        
        # Висота сітки
        grid_height = grid_cell_height * constructor_rows
        controls_panel_y = grid_start_y + grid_height + 10  # 10px відступ під сіткою
        controls_panel_x = 10
        
        # Заголовок з інформацією про поточний шар
        layer_info = ft.Container(
            content=ft.Text(
                f"Шар {constructor_current_layer + 1} з {len(constructor_pattern)}",
                size=14,
                weight=ft.FontWeight.BOLD,
                color="#FFFFFF",
            ),
            left=controls_panel_x,
            top=controls_panel_y,
        )
        board_container.controls.append(layer_info)
        
        # Кнопка "+1 шар"
        def add_layer(e):
            nonlocal constructor_pattern, constructor_current_layer
            # Додаємо новий шар
            new_layer = [[False for _ in range(constructor_cols)] for _ in range(constructor_rows)]
            constructor_pattern.append(new_layer)
            # Перемикаємося на новий шар
            constructor_current_layer = len(constructor_pattern) - 1
            print(f"DEBUG add_layer: Додано новий шар. Всього шарів: {len(constructor_pattern)}, поточний: {constructor_current_layer}")
            update_board()
            page.update()
        
        add_layer_button = ft.ElevatedButton(
            "+1 шар",
            width=180,
            height=40,
            bgcolor="#4CAF50",
            color="#FFFFFF",
            on_click=add_layer,
        )
        board_container.controls.append(
            ft.Container(
                content=add_layer_button,
                left=controls_panel_x + 200,
                top=controls_panel_y,
            )
        )
        
        # Кнопка "Видалити шар" (тільки якщо є більше одного шару)
        def delete_layer(e):
            nonlocal constructor_pattern, constructor_current_layer
            if len(constructor_pattern) > 1:
                # Видаляємо поточний шар
                del constructor_pattern[constructor_current_layer]
                # Якщо видалили останній шар, переходимо на попередній
                if constructor_current_layer >= len(constructor_pattern):
                    constructor_current_layer = len(constructor_pattern) - 1
                update_board()
                page.update()
            else:
                # Показуємо повідомлення, що не можна видалити останній шар
                page.snack_bar = ft.SnackBar(ft.Text("Не можна видалити останній шар"), open=True)
                page.update()
        
        delete_layer_button = ft.ElevatedButton(
            "Видалити шар",
            width=180,
            height=40,
            # Робимо стилем як кнопка "Режими" у сайдбарі
            bgcolor="#4CAF50" if len(constructor_pattern) > 1 else "#999999",
            color="#FFFFFF",
            on_click=delete_layer,
            disabled=len(constructor_pattern) <= 1,
        )
        board_container.controls.append(
            ft.Container(
                content=delete_layer_button,
                # 5px відступ від попередньої кнопки (180 + 5)
                left=controls_panel_x + 385,
                top=controls_panel_y,
            )
        )
        
        # Кнопки для перемикання між шарами
        for layer_idx in range(len(constructor_pattern)):
            def switch_to_layer(e, layer=layer_idx):
                nonlocal constructor_current_layer
                constructor_current_layer = layer
                update_board()
                page.update()
            
            # Кнопка шару: компактна, ширина визначається текстом ("Шар N"),
            # щоб усі шари поміщалися в одному рядку
            layer_button = ft.ElevatedButton(
                f"Шар {layer_idx + 1}",
                height=40,
                bgcolor="#4CAF50" if layer_idx == constructor_current_layer else "#388E3C",
                color="#FFFFFF",
                on_click=switch_to_layer,
            )
            board_container.controls.append(
                ft.Container(
                    content=layer_button,
                    # Починаємо після кнопок "+1 шар" і "Видалити шар"
                    # Орієнтовна ширина маленької кнопки шару ~80px, додаємо 5px між ними
                    left=controls_panel_x + 570 + layer_idx * 85,
                    top=controls_panel_y,
                )
            )
        
        # Поле для назви патерну та кнопка "Зберегти"
        # Якщо є завантажений патерн, використовуємо його назву
        initial_pattern_name = constructor_loaded_pattern_name if constructor_loaded_pattern_name else ""
        pattern_name_field = ft.TextField(
            label="Назва патерну",
            width=200,
            height=40,
            hint_text="Введіть назву",
            value=initial_pattern_name,  # Встановлюємо значення при створенні
        )
        print(f"DEBUG render_constructor_controls: Створено pattern_name_field з value='{initial_pattern_name}' (constructor_loaded_pattern_name='{constructor_loaded_pattern_name}')")
        board_container.controls.append(
            ft.Container(
                content=pattern_name_field,
                left=controls_panel_x,
                top=controls_panel_y + 50,
            )
        )
        
        def save_pattern(e):
            nonlocal constructor_pattern, constructor_loaded_pattern_name, constructor_game_mode
            pattern_name = pattern_name_field.value.strip()
            if not pattern_name:
                page.snack_bar = ft.SnackBar(ft.Text("Введіть назву патерну"), open=True)
                page.update()
                return
            
            # Підраховуємо кількість позначених місць
            total_marked = 0
            for layer in constructor_pattern:
                for row in layer:
                    total_marked += sum(1 for cell in row if cell)
            
            if total_marked == 0:
                page.snack_bar = ft.SnackBar(ft.Text("Патерн порожній. Позначте хоча б одне місце для тейла"), open=True)
                page.update()
                return
            
            # Створюємо папку для патернів, якщо її немає
            patterns_dir = Path("patterns")
            patterns_dir.mkdir(exist_ok=True)
            
            # Визначаємо, чи це редагування існуючого патерну
            is_editing = constructor_loaded_pattern_name is not None
            old_pattern_file = None
            
            if is_editing:
                # Якщо редагуємо існуючий патерн, знаходимо старий файл
                pattern_files_list, _ = refresh_pattern_dropdown()
                for pf in pattern_files_list:
                    try:
                        with open(pf, "r", encoding="utf-8") as f:
                            pattern_data = json.load(f)
                        if pattern_data.get("name", pf.stem) == constructor_loaded_pattern_name:
                            old_pattern_file = pf
                            break
                    except:
                        if pf.stem == constructor_loaded_pattern_name:
                            old_pattern_file = pf
                            break
            
            # Перевіряємо, чи патерн з новою назвою вже існує
            pattern_file = patterns_dir / f"{pattern_name}.json"
            pattern_exists = pattern_file.exists()
            
            # Якщо редагуємо і назва змінилася, і новий файл вже існує (інший патерн з такою назвою)
            if is_editing and pattern_name != constructor_loaded_pattern_name and pattern_exists:
                page.snack_bar = ft.SnackBar(ft.Text(f"Патерн з назвою '{pattern_name}' вже існує. Оберіть іншу назву"), open=True)
                page.update()
                return
            
            # Зберігаємо патерн
            pattern_data = {
                "name": pattern_name,
                "cols": constructor_cols,
                "rows": constructor_rows,
                "layers": constructor_pattern,
                "game_mode": constructor_game_mode,  # Зберігаємо тип пасьянсу
            }
            
            # Якщо це редагування існуючого патерну
            if is_editing:
                # Завантажуємо старий патерн, щоб зберегти created_at
                if old_pattern_file and old_pattern_file.exists():
                    try:
                        with open(old_pattern_file, "r", encoding="utf-8") as f:
                            existing_data = json.load(f)
                        pattern_data["created_at"] = existing_data.get("created_at", datetime.now().isoformat())
                    except:
                        pattern_data["created_at"] = datetime.now().isoformat()
                    
                    # Якщо назва змінилася, видаляємо старий файл
                    if pattern_name != constructor_loaded_pattern_name:
                        old_pattern_file.unlink()
                        print(f"DEBUG save_pattern: Видалено старий файл '{old_pattern_file}' після зміни назви")
                else:
                    pattern_data["created_at"] = datetime.now().isoformat()
                
                pattern_data["updated_at"] = datetime.now().isoformat()
                message = f"Патерн '{pattern_name}' оновлено! Позначено місць: {total_marked}"
                # Оновлюємо назву завантаженого патерну
                constructor_loaded_pattern_name = pattern_name
            elif pattern_exists:
                # Якщо патерн існує (але не редагуємо) - оновлюємо
                try:
                    with open(pattern_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                    pattern_data["created_at"] = existing_data.get("created_at", datetime.now().isoformat())
                except:
                    pattern_data["created_at"] = datetime.now().isoformat()
                pattern_data["updated_at"] = datetime.now().isoformat()
                message = f"Патерн '{pattern_name}' оновлено! Позначено місць: {total_marked}"
            else:
                # Створюємо новий патерн
                pattern_data["created_at"] = datetime.now().isoformat()
                message = f"Патерн '{pattern_name}' збережено! Позначено місць: {total_marked}"
            
            # Зберігаємо в JSON файл
            with open(pattern_file, "w", encoding="utf-8") as f:
                json.dump(pattern_data, f, indent=2, ensure_ascii=False)
            
            page.snack_bar = ft.SnackBar(ft.Text(message), open=True)
            print(f"DEBUG save_pattern: {'Оновлено' if (is_editing or pattern_exists) else 'Збережено'} патерн '{pattern_name}' з {total_marked} позначеними місцями")
            # Оновлюємо випадаюче меню, щоб показати новий патерн
            refresh_pattern_dropdown()
            # Оновлюємо меню для solitaire1 та solitaire2
            refresh_solitaire1_dropdown()
            refresh_solitaire2_dropdown()
            # Оновлюємо інтерфейс
            update_board()
            page.update()
        
        save_button = ft.ElevatedButton(
            "Зберегти патерн",
            width=180,
            height=40,
            bgcolor="#4CAF50",
            color="#FFFFFF",
            on_click=save_pattern,
        )
        board_container.controls.append(
            ft.Container(
                content=save_button,
                # 5px відступ від поля назви (200px ширини)
                left=controls_panel_x + 205,
                top=controls_panel_y + 50,
            )
        )
        
        # Випадаюче меню збережених патернів
        # Спочатку завантажуємо список патернів
        patterns_dir = Path("patterns")
        pattern_files = []
        pattern_names = []
        if patterns_dir.exists():
            pattern_files = sorted(patterns_dir.glob("*.json"))
            for pattern_file in pattern_files:
                try:
                    with open(pattern_file, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    pattern_names.append(pattern_data.get("name", pattern_file.stem))
                except:
                    pattern_names.append(pattern_file.stem)
        
        # Створюємо випадаюче меню
        pattern_dropdown = ft.Dropdown(
            label="Збережені патерни",
            width=200,
            options=[ft.dropdown.Option(name) for name in pattern_names] if pattern_names else [],
            value=None,
        )
        
        # Функція для оновлення списку патернів
        def refresh_pattern_dropdown():
            """Оновлює список патернів у випадаючому меню"""
            patterns_dir = Path("patterns")
            pattern_files_list = []
            pattern_names_list = []
            if patterns_dir.exists():
                pattern_files_list = sorted(patterns_dir.glob("*.json"))
                for pattern_file in pattern_files_list:
                    try:
                        with open(pattern_file, "r", encoding="utf-8") as f:
                            pattern_data = json.load(f)
                        pattern_names_list.append(pattern_data.get("name", pattern_file.stem))
                    except:
                        pattern_names_list.append(pattern_file.stem)
            
            pattern_dropdown.options = [ft.dropdown.Option(name) for name in pattern_names_list] if pattern_names_list else []
            pattern_dropdown.value = None
            return pattern_files_list, pattern_names_list
        
        # Функція для завантаження патерну
        def load_pattern_for_edit(e):
            nonlocal constructor_pattern, constructor_current_layer, constructor_loaded_pattern_name, constructor_game_mode
            selected_name = pattern_dropdown.value
            if not selected_name:
                page.snack_bar = ft.SnackBar(ft.Text("Виберіть патерн зі списку"), open=True)
                page.update()
                return
            
            # Оновлюємо список файлів
            pattern_files_list, _ = refresh_pattern_dropdown()
            
            # Знаходимо файл патерну
            pattern_file = None
            for pf in pattern_files_list:
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    if pattern_data.get("name", pf.stem) == selected_name:
                        pattern_file = pf
                        break
                except:
                    if pf.stem == selected_name:
                        pattern_file = pf
                        break
            
            if not pattern_file:
                page.snack_bar = ft.SnackBar(ft.Text("Патерн не знайдено"), open=True)
                page.update()
                return
            
            try:
                with open(pattern_file, "r", encoding="utf-8") as f:
                    pattern_data = json.load(f)
                
                # Завантажуємо патерн
                if "layers" in pattern_data:
                    constructor_pattern = []
                    for layer in pattern_data["layers"]:
                        converted_layer = []
                        for row in layer:
                            converted_row = [bool(cell) for cell in row]
                            converted_layer.append(converted_row)
                        constructor_pattern.append(converted_layer)
                    
                    constructor_current_layer = 0
                    
                    # Заповнюємо поле назви
                    loaded_pattern_name = pattern_data.get("name", selected_name)
                    if not loaded_pattern_name:
                        loaded_pattern_name = selected_name
                    
                    # Зберігаємо назву завантаженого патерну
                    constructor_loaded_pattern_name = loaded_pattern_name
                    
                    # Встановлюємо тип пасьянсу з патерну (якщо є)
                    # За замовчуванням старі патерни вважаємо для Пасьянсу 2 (історично конструктор був для нього)
                    loaded_game_mode = pattern_data.get("game_mode", "solitaire2")
                    # Нормалізуємо можливі старі текстові значення
                    if loaded_game_mode in ("Пасьянс 1", "solitaire1"):
                        loaded_game_mode = "solitaire1"
                    elif loaded_game_mode in ("Пасьянс 2", "solitaire2"):
                        loaded_game_mode = "solitaire2"
                    constructor_game_mode = loaded_game_mode
                    print(f"DEBUG load_pattern_for_edit: Завантажено патерн '{loaded_pattern_name}' (selected_name='{selected_name}'), game_mode={loaded_game_mode}")
                    
                    page.snack_bar = ft.SnackBar(ft.Text(f"Патерн '{loaded_pattern_name}' завантажено для редагування"), open=True)
                    # Оновлюємо дошку (це очистить controls і перестворює pattern_name_field з правильним значенням)
                    # Значення встановлюється автоматично в render_constructor_controls() через constructor_loaded_pattern_name
                    update_board()
                    # Оновлюємо UI
                    page.update()
                else:
                    page.snack_bar = ft.SnackBar(ft.Text("Помилка: некоректний формат патерну"), open=True)
                    page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Помилка завантаження: {ex}"), open=True)
                page.update()
        
        # Кнопка "Завантажити" для вибраного патерну
        load_button = ft.ElevatedButton(
            "Завантажити",
            width=180,
            height=40,
            bgcolor="#4CAF50",
            color="#FFFFFF",
            on_click=load_pattern_for_edit,
        )
        
        # Функція для видалення патерну
        def delete_pattern(e):
            nonlocal constructor_loaded_pattern_name
            # Спочатку перевіряємо, чи є завантажений патерн
            selected_name = constructor_loaded_pattern_name or pattern_dropdown.value
            if not selected_name:
                page.snack_bar = ft.SnackBar(ft.Text("Виберіть патерн для видалення або завантажте патерн"), open=True)
                page.update()
                return
            
            # Оновлюємо список файлів
            pattern_files_list, _ = refresh_pattern_dropdown()
            
            # Знаходимо файл патерну
            pattern_file = None
            for pf in pattern_files_list:
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    if pattern_data.get("name", pf.stem) == selected_name:
                        pattern_file = pf
                        break
                except:
                    if pf.stem == selected_name:
                        pattern_file = pf
                        break
            
            if not pattern_file:
                page.snack_bar = ft.SnackBar(ft.Text("Патерн не знайдено"), open=True)
                page.update()
                return
            
            try:
                pattern_file.unlink()
                print(f"DEBUG delete_pattern: Файл '{pattern_file}' видалено")
                page.snack_bar = ft.SnackBar(ft.Text(f"Патерн '{selected_name}' видалено"), open=True)
                # Очищаємо поле конструктора
                nonlocal constructor_pattern
                constructor_pattern = []
                constructor_loaded_pattern_name = None
                # Ініціалізуємо порожній патерн
                initialize_pattern_constructor()
                # Оновлюємо список у випадаючому меню
                refresh_pattern_dropdown()
                # Оновлюємо меню для solitaire1 та solitaire2
                refresh_solitaire1_dropdown()
                refresh_solitaire2_dropdown()
                # Очищаємо вибір у dropdown
                pattern_dropdown.value = None
                update_board()
                page.update()
                print(f"DEBUG delete_pattern: Патерн '{selected_name}' видалено, поле очищено, меню оновлено")
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Помилка видалення: {ex}"), open=True)
                page.update()
        
        # Кнопка "Редагувати" (викликає ту саму функцію, що і "Завантажити")
        edit_button = ft.ElevatedButton(
            "Редагувати",
            width=180,
            height=40,
            bgcolor="#4CAF50",
            color="#FFFFFF",
            on_click=load_pattern_for_edit,
        )
        
        # Кнопка "Видалити"
        delete_button = ft.ElevatedButton(
            "Видалити",
            width=180,
            height=40,
            bgcolor="#4CAF50",
            color="#FFFFFF",
            on_click=delete_pattern,
        )
        
        # Розміщуємо випадаюче меню та кнопки
        board_container.controls.append(
            ft.Container(
                content=pattern_dropdown,
                left=controls_panel_x,
                top=controls_panel_y + 100,
            )
        )
        board_container.controls.append(
            ft.Container(
                content=load_button,
                # 5px відступ від dropdown (200px ширини)
                left=controls_panel_x + 205,
                top=controls_panel_y + 100,
            )
        )
        board_container.controls.append(
            ft.Container(
                content=edit_button,
                # 180 (ширина кнопки) + 5px відступ
                left=controls_panel_x + 390,
                top=controls_panel_y + 100,
            )
        )
        board_container.controls.append(
            ft.Container(
                content=delete_button,
                # ще 180 + 5px
                left=controls_panel_x + 575,
                top=controls_panel_y + 100,
            )
        )
    
    def constructor_cell_clicked(z: int, y: int, x: int):
        """Обробляє клік по клітинці конструктора - перемикає позначку місця для тейла"""
        nonlocal constructor_pattern, constructor_current_layer
        
        # Використовуємо поточний активний шар
        current_z = constructor_current_layer
        
        # Переконаємося, що шар існує
        if current_z >= len(constructor_pattern):
            while len(constructor_pattern) <= current_z:
                constructor_pattern.append([[False for _ in range(constructor_cols)] for _ in range(constructor_rows)])
        
        # Перемикаємо позначку: True -> False, False -> True
        constructor_pattern[current_z][y][x] = not constructor_pattern[current_z][y][x]
        print(f"DEBUG constructor_cell_clicked: {'Позначено' if constructor_pattern[current_z][y][x] else 'Знято позначку'} місце для тейла на ({x},{y},{current_z})")
        
        update_board()
        page.update()
    
    def render_tile_palette():
        """Панель заготовок тейлів більше не використовується - просто очищаємо контейнер"""
        nonlocal tile_palette_container
        # Очищаємо контейнер панелі тейлів (більше не потрібна)
        tile_palette_container.controls.clear()
    
    def save_pattern():
        """Зберігає патерн під назвою"""
        nonlocal constructor_pattern
        # TODO: Додати діалог введення назви та збереження
        print(f"DEBUG save_pattern: Зберігаю патерн (TODO: діалог введення назви)")
        page.snack_bar = ft.SnackBar(ft.Text("Функція збереження в розробці"), open=True)
        page.update()
    
    def show_modes_page(e):
        """Показує сторінку вибору режимів та ігор"""
        nonlocal start_button, duel_button, duel2_button, board, current_session_id, end_game_overlay, finish_text_container
        # Приховуємо напис фінішу при виборі режимів
        if finish_text_container:
            finish_text_container.visible = False
        print(f"DEBUG show_modes_page: Викликано")
        print(f"DEBUG show_modes_page: current_profile['id']={current_profile['id']}")
        print(f"DEBUG show_modes_page: board={board}")
        print(f"DEBUG show_modes_page: board.game_over={board.game_over if board else 'None'}")
        print(f"DEBUG show_modes_page: current_session_id={current_session_id}")
        
        # Перевіряємо, чи гра активна (не завершена і є активна сесія)
        is_game_active = board and not board.game_over and current_session_id is not None
        print(f"DEBUG show_modes_page: is_game_active={is_game_active}")
        
        if is_game_active:
            print(f"DEBUG show_modes_page: Гра активна, показую діалог підтвердження")
            nonlocal end_game_overlay
            # Створюємо overlay, якщо він ще не створений
            if end_game_overlay is None:
                print(f"DEBUG show_modes_page: Створюю end_game_overlay")
                end_game_overlay = ft.Container(
                    expand=True,
                    bgcolor="#000000DD",
                    alignment=ft.alignment.center,
                    content=ft.Container(
                        width=400,
                        height=200,
                        padding=20,
                        bgcolor="#1E1E1E",
                        border_radius=10,
                        content=ft.Column(
                            [
                                ft.Text("Завершити гру?", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                                ft.Divider(height=10),
                                ft.Text("Чи дійсно завершити поточну гру?", size=14, color="#FFFFFF"),
                                ft.Container(height=20),
                                ft.Row(
                                    [
                                        ft.ElevatedButton("Так", on_click=confirm_end_game_and_show_modes, width=100, bgcolor="#4CAF50"),
                                        ft.ElevatedButton("Ні", on_click=lambda e: close_end_game_dialog(), width=100, bgcolor="#666666"),
                                    ],
                                    alignment=ft.MainAxisAlignment.END,
                                    spacing=10,
                                ),
                            ],
                            spacing=8,
                            tight=True,
                        ),
                    ),
                    visible=False,
                )
            
            if end_game_overlay not in page.overlay:
                page.overlay.append(end_game_overlay)
            end_game_overlay.visible = True
            print(f"DEBUG show_modes_page: end_game_overlay.visible встановлено в True, викликаю page.update()")
            page.update()
            print(f"DEBUG show_modes_page: page.update() викликано")
            return
        
        # Якщо гра не активна, просто показуємо режими
        print(f"DEBUG show_modes_page: Гра не активна, показую режими безпосередньо")
        show_modes_page_internal()
    
    modes_button = ft.ElevatedButton(
        "Режими",
        width=180,
        bgcolor="#4CAF50",
        color="#FFFFFF",
        on_click=show_modes_page,
    )
    
    # Розділяємо sidebar на 3 частини
    # Частина 1: Інформація про користувача та кнопки
    def logout_user(e):
        """Вихід користувача з акаунту"""
        nonlocal current_profile, current_session_id, game_records, profile_label, auth_overlay_container
        # Закриваємо поточну сесію, якщо вона активна
        if current_session_id is not None:
            end_session(current_session_id, "Вихід", hints_used=0, shuffle_used=0)
            current_session_id = None
        
        # Скидаємо профіль
        current_profile["id"] = None
        current_profile["username"] = None
        current_profile["role"] = None
        profile_label.value = "Гравець: (не вхід)"
        game_records = []
        
        # Оновлюємо статистику
        refresh_profile_stats()
        refresh_records_table()
        
        # Оновлюємо sidebar
        update_sidebar()
        
        # Показуємо діалог входу
        show_auth_dialog()
        
        # Оновлюємо дошку
        update_board()
        page.update()
    
    cabinet_button = ft.TextButton(
        "Кабінет",
        on_click=show_cabinet_dialog,
    )
    
    logout_button = ft.ElevatedButton(
        "Вийти",
        width=180,
        bgcolor="#FF6B6B",
        color="#FFFFFF",
        on_click=logout_user,
    )
    
    sidebar_part1 = ft.Container(
        content=ft.Column(
            [
                # Блок 1: Інформація про користувача
                profile_label,
                cabinet_button,
                games_label,
                logout_button,
                ft.Divider(height=1, color="#2b2b2b"),  # Розділювач між блоками
                # Блок 2: Кнопки гри
                hint_button,
                shuffle_button,
                pause_button,
                leaderboard_button,
                # Адмінська кнопка доступна тільки для користувача з роллю admin
                *([admin_button] if current_profile.get("role") == "admin" else []),
                ft.Divider(height=1, color="#2b2b2b"),  # Розділювач перед таймером
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Таймер", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                            ft.Container(
                                content=timer_text,
                                padding=ft.padding.only(left=5),  # Зсуваємо час вправо на 5 пікселів
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        tight=True,
                    ),
                    alignment=ft.alignment.center,
                ),
            ],
            spacing=8,  # Зменшено spacing з 12 до 8
            tight=True,
        ),
        padding=ft.padding.symmetric(horizontal=12, vertical=8),  # Зменшено vertical padding
    )
    
    # Частина 2: Кращий час для обох пасьянсів
    sidebar_part2 = ft.Container(
        content=ft.Column(
            [
                ft.Text("Кращий час", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                best_time_s1_label,
                best_time_s2_label,
            ],
            spacing=8,
            tight=True,
        ),
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
        visible=False,  # Початково прихована, поки користувач не увійде
    )
    
    # Divider для таблиці рекордів
    sidebar_part2_divider = ft.Divider(height=1, color="#2b2b2b", visible=False)
    
    # Частина 3: Кнопки Support та Режими внизу (завжди видимі)
    sidebar_part3 = ft.Container(
        content=ft.Column(
            [
                modes_button,
                support_button,
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.all(12),
        alignment=ft.alignment.center,
    )
    
    # Частина 4: Coins (монети для донату)
    coins_label = ft.Text("Coins: 0", size=16, weight=ft.FontWeight.BOLD, color="#FFD700")
    
    def buy_hint_button_click(e):
        """Обробник натискання кнопки купівлі підказки"""
        if current_profile["id"] is None:
            page.snack_bar = ft.SnackBar(ft.Text("Увійди, щоб купувати"), open=True)
            page.update()
            return
        if buy_hint(current_profile["id"]):
            page.snack_bar = ft.SnackBar(ft.Text("Куплено +1 підказка за 1 coin"), open=True)
            # Оновлюємо hints_remaining: базові (2) + куплені з бази даних
            nonlocal hints_remaining
            # Завжди оновлюємо hints_remaining з бази даних для синхронізації
            # Базові 2 підказки + куплені з бази даних
            hints_remaining = 2 + get_user_hints(current_profile["id"])
            # Оновлюємо sidebar (coins)
            update_sidebar()
            # Оновлюємо інтерактивно кнопку підказки в області 1 (навіть якщо гра не активна)
            hint_button.text = f"Підказка ({hints_remaining}/2)"
            hint_button.update()
            # Якщо гра активна, оновлюємо весь UI кнопок
            if board and not board.game_over:
                update_action_ui()
            # Підказка додана до бази даних і буде доступна в наступній грі
        else:
            page.snack_bar = ft.SnackBar(ft.Text("Недостатньо монет"), open=True)
        page.update()
    
    def buy_shuffle_button_click(e):
        """Обробник натискання кнопки купівлі тасування"""
        if current_profile["id"] is None:
            page.snack_bar = ft.SnackBar(ft.Text("Увійди, щоб купувати"), open=True)
            page.update()
            return
        if buy_shuffle(current_profile["id"]):
            page.snack_bar = ft.SnackBar(ft.Text("Куплено +1 тасування за 1 coin"), open=True)
            # Оновлюємо shuffle_remaining: базові (1) + куплені з бази даних
            nonlocal shuffle_remaining
            # Завжди оновлюємо shuffle_remaining з бази даних для синхронізації
            # Базові 1 тасування + куплені з бази даних
            shuffle_remaining = 1 + get_user_shuffles(current_profile["id"])
            # Оновлюємо sidebar (coins)
            update_sidebar()
            # Оновлюємо інтерактивно кнопку тасування в області 1 (навіть якщо гра не активна)
            shuffle_button.text = f"Тасування ({shuffle_remaining}/1)"
            shuffle_button.update()
            # Якщо гра активна, оновлюємо весь UI кнопок
            if board and not board.game_over:
                update_action_ui()
            # Тасування додане до бази даних і буде доступне в наступній грі
        else:
            page.snack_bar = ft.SnackBar(ft.Text("Недостатньо монет"), open=True)
        page.update()
    
    buy_hint_button = ft.ElevatedButton(
        "+1 підказка (1 coin)",
        width=180,
        bgcolor="#4CAF50",
        color="#FFFFFF",
        on_click=buy_hint_button_click,
    )
    
    buy_shuffle_button = ft.ElevatedButton(
        "+1 тасування (1 coin)",
        width=180,
        bgcolor="#4CAF50",
        color="#FFFFFF",
        on_click=buy_shuffle_button_click,
    )
    
    sidebar_part4 = ft.Container(
        content=ft.Column(
            [
                coins_label,
                buy_hint_button,
                buy_shuffle_button,
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.padding.all(12),
        alignment=ft.alignment.center,
    )
    
    # Створюємо динамічний sidebar, який змінюється залежно від стану входу
    def update_sidebar():
        """Оновлює вміст sidebar залежно від стану входу користувача"""
        # Показуємо/приховуємо таблицю рекордів залежно від стану входу
        if current_profile["id"] is not None:
            sidebar_part2.visible = True
            sidebar_part2_divider.visible = True
            # Оновлюємо coins
            coins = get_user_coins(current_profile["id"])
            coins_label.value = f"Coins: {coins}"
            # Оновлюємо підказки та тасування (базові + куплені з бази даних)
            nonlocal hints_remaining, shuffle_remaining
            hints_remaining = 2 + get_user_hints(current_profile["id"])
            shuffle_remaining = 1 + get_user_shuffles(current_profile["id"])
            # Оновлюємо інтерактивно кнопки в області 1
            hint_button.text = f"Підказка ({hints_remaining}/2)"
            shuffle_button.text = f"Тасування ({shuffle_remaining}/1)"
        else:
            sidebar_part2.visible = False
            sidebar_part2_divider.visible = False
            coins_label.value = "Coins: 0"
        page.update()
    
    # Створюємо прозору частину для комірок (50px зліва) та видиму частину сайдбару (200px справа)
    sidebar_visible = ft.Container(
        width=200,  # Видима частина сайдбару
        height=730,
        bgcolor=UI_PANEL_COLOR,
        border=ft.border.all(1, "#2b2b2b"),
        border_radius=10,
        content=ft.Column(
            [
                sidebar_part1,  # Верхня частина - інформація та кнопки
                sidebar_part2_divider,  # Divider для таблиці рекордів
                sidebar_part2,  # Середня частина - таблиця рекордів (початково прихована)
                ft.Divider(height=1, color="#2b2b2b"),  # Divider перед кнопкою Support
                sidebar_part3,  # Нижня частина - кнопка Support завжди видима
                ft.Divider(height=1, color="#2b2b2b"),  # Divider перед coins
                sidebar_part4,  # Найнижча частина - coins
            ],
            spacing=0,
            expand=False,  # Прибрано expand, щоб не було пустого поля
        ),
    )
    
    # Прозора частина для комірок (60px зліва)
    sidebar_slots_area = ft.Container(
        width=60,  # Збільшено з 50 до 60 пікселів
        height=730,
        bgcolor=None,  # Прозорий фон
        border=None,
        content=ft.Stack([]),  # Ініціалізуємо Stack для комірок
    )
    
    # Об'єднуємо прозору частину та видиму частину сайдбару
    sidebar = ft.Container(
        width=260,  # Збільшено з 250 до 260 (60 прозора + 200 видима)
        height=730,
        margin=ft.margin.only(top=10),  # Глобальний відступ зверху, як у тейлів
        content=ft.Row(
            [
                sidebar_slots_area,  # Прозора частина для комірок (60px)
                sidebar_visible,  # Видима частина сайдбару (200px)
            ],
            spacing=0,
            expand=False,
        ),
    )
    content_row = ft.Container(
        content=ft.Row(
            [
                ft.Container(content=board_container, width=1100, height=790, alignment=ft.alignment.top_left),
                sidebar,
            ],
            spacing=12,
            expand=False,  # Прибрано expand, щоб не було пустого поля
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,  # Розтягуємо, щоб сайдбар був справа
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        margin=ft.margin.only(left=10, right=10),  # Глобальні відступи зліва і справа (10 пікселів)
    )
    # Створюємо головний контейнер з Stack для overlay
    main_stack = ft.Stack(
        [
            content_row,
            tile_palette_container,  # Панель тейлів поверх сайдбару
        ],
        expand=False,  # Прибрано expand, щоб не було пустого поля
    )
    print(f"DEBUG: main_stack створено, controls count={len(main_stack.controls)}")
    update_action_ui()
    def is_tile_darkened_solitaire2(tile: Tile) -> bool:
        """Перевіряє, чи тейл має бути затемнений для Пасьянс-2"""
        # Тейл затемнений, якщо:
        # 1. Він закритий з обох сторін (лівої і правої одночасно) АБО
        # 2. Зверху є тейл
        
        # Перевіряємо, чи є тейл зверху
        has_tile_on_top = any(
            other_tile is not tile
            and not other_tile.removed
            and other_tile.x == tile.x
            and other_tile.y == tile.y
            and other_tile.z > tile.z
            for other_tile in board.tiles
        )
        
        if has_tile_on_top:
            return True
        
        # Перевіряємо ліву та праву сторони
        def has_neighbor(dx: int, dy: int) -> bool:
            return any(
                other_tile is not tile
                and not other_tile.removed
                and other_tile.z == tile.z
                and other_tile.x == tile.x + dx
                and other_tile.y == tile.y + dy
                for other_tile in board.tiles
            )
        
        left_blocked = has_neighbor(-1, 0)  # Зліва
        right_blocked = has_neighbor(1, 0)  # Справа
        
        # Тейл затемнений, якщо закритий і зліва, і справа
        return left_blocked and right_blocked
    
    def create_tile_container(tile: Tile) -> ft.Container:
        """Створює контейнер для плитки"""
        global game_mode
        board_start_x = 10
        # Глобальний відступ зверху для всіх режимів
        board_start_y = 10

        # Для Пасьянс 2 додаємо зміщення залежно від рівня (z)
        # Тейли на вищих рівнях зміщуються вправо-вниз для 3D ефекту
        # Збільшуємо зміщення для кращої видимості вищих рівнів
        # Зміщення для шарів: трохи вгору і вправо для вищих рівнів
        z_offset_x = tile.z * 5 if game_mode == "solitaire2" else 0  # Зміщення вправо для вищих рівнів (5px на шар)
        z_offset_y = -tile.z * 5 if game_mode == "solitaire2" else 0  # Зміщення вгору для вищих рівнів (5px на шар)
        
        screen_x = board_start_x + tile.x * TILE_SPACING_X + z_offset_x
        screen_y = board_start_y + tile.y * TILE_SPACING_Y + z_offset_y

        if tile.highlighted:
            border_color = HINT_COLOR
            border_width = 4
            tile_bgcolor = "#FFF9D5"
        else:
            # Прибираємо обводку для звичайних тейлів, залишаємо тільки для вибраних
            border_color = SELECTED_COLOR if tile.selected else None
            border_width = 1 if tile.selected else 0  # Тонка обводка 1 піксель для вибраних тейлів
            tile_bgcolor = TILE_COLOR

        # Для Пасьянс-2: затемнюємо тейли, які закриті з обох сторін АБО зверху (якщо режим увімкнено)
        is_darkened = False
        if game_mode == "solitaire2" and darken_mode:
            is_darkened = is_tile_darkened_solitaire2(tile)

        if tile.tile_type in tile_images:
            tile_content = ft.Image(
                src=tile_images[tile.tile_type],
                width=TILE_WIDTH,
                height=TILE_HEIGHT,
                fit=ft.ImageFit.CONTAIN,
            )
        else:
            tile_content = ft.Container(
                content=ft.Text(
                    tile.get_display_name(),
                    size=16,
                    color="#000000",
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.alignment.center,
                width=TILE_WIDTH,
                height=TILE_HEIGHT,
                bgcolor=TILE_COLOR,
            )
        
        # Якщо тейл затемнений - додаємо темний overlay поверх зображення
        if is_darkened:
            # Створюємо Stack з тейлом і темним overlay
            darkened_content = ft.Stack(
                [
                    tile_content,
                    ft.Container(
                        width=TILE_WIDTH,
                        height=TILE_HEIGHT,
                        bgcolor="#000000",  # Чорний overlay
                        opacity=0.5,  # Прозорість overlay (не самого тейла!)
                        border_radius=5,
                    ),
                ],
                width=TILE_WIDTH,
                height=TILE_HEIGHT,
            )
            final_content = darkened_content
        else:
            final_content = tile_content

        container = ft.Container(
            content=final_content,
            left=screen_x,
            top=screen_y,
            width=TILE_WIDTH,
            height=TILE_HEIGHT,
            border=ft.border.all(border_width, border_color) if border_color else None,
            border_radius=5,
            shadow=ft.BoxShadow(
                spread_radius=1,
                blur_radius=8,
                color="#00000066",
                offset=ft.Offset(2, 3),
            ),
            opacity=1.0,  # Контейнер завжди повністю непрозорий
            on_click=lambda e, t=tile: tile_clicked(t),
        )

        tile.ui_element = container
        return container
    
    def tile_clicked(tile: Tile):
        """Обробник кліку по плитці"""
        global game_mode
        nonlocal solitaire2_slots, solitaire2_last_move
        
        # Перевіряємо, чи гра почалася
        if start_button and start_button.visible:
            return
        if is_paused:
            return
        if current_profile["id"] is None:
            page.snack_bar = ft.SnackBar(ft.Text("Увійди, щоб грати"), open=True)
            page.update()
            show_auth_dialog()
            return
        nonlocal timer_started
        if not timer_started and not board.game_over:
            start_timer(reset=True)
        
        # Для Пасьянс 2 - нова логіка з комірками
        if game_mode == "solitaire2":
            nonlocal solitaire2_last_move, solitaire2_slots, solitaire2_pending_removal
            
            # Перевіряємо, чи тейл доступний для видалення
            is_available = board.is_tile_available(tile)
            print(f"DEBUG tile_clicked solitaire2: tile=({tile.x},{tile.y},{tile.z}), tile_type={tile.tile_type}, is_available={is_available}, removed={tile.removed}")
            if not is_available or tile.removed:
                print(f"DEBUG tile_clicked solitaire2: Тейл недоступний або вже видалений")
                return
            
            # ВАЖЛИВО: Якщо обидві комірки зайняті, перевіряємо, чи натиснутий тейл відповідає одному з тейлів у комірках
            # Якщо так - видаляємо обидва (тейл на полі і тейл у комірці)
            if solitaire2_slots[0] is not None and solitaire2_slots[1] is not None:
                # Обидві комірки зайняті - перевіряємо на відповідність
                slot_tile = None
                slot_index = None
                print(f"DEBUG tile_clicked solitaire2: Обидві комірки зайняті, перевіряю на відповідність з тейлом на полі")
                
                # Перевіряємо на відповідність з тейлами в комірках
                for i, slot_t in enumerate(solitaire2_slots[:2]):  # Тільки перші 2 комірки
                    if slot_t is not None:
                        is_match = slot_t.tile_type == tile.tile_type
                        print(f"DEBUG tile_clicked solitaire2: Комірка {i}: tile_type={slot_t.tile_type}, порівняння з {tile.tile_type}: {is_match}")
                        if is_match:
                            print(f"DEBUG tile_clicked solitaire2: ✓ Знайдено відповідний тейл у комірці {i} - видаляю обидва")
                            slot_tile = slot_t
                            slot_index = i
                            break
                
                if slot_tile is not None:
                    # Знайдено відповідний тейл у комірці - видаляємо обидва одразу
                    solitaire2_last_move = None
                    solitaire2_pending_removal = False
                    
                    tile.removed = True
                    slot_tile.removed = True
                    solitaire2_slots[slot_index] = None
                    update_board()
                    page.update()
                    check_game_state()
                    return  # Виходимо, бо тейли вже видалені
            
            # Якщо комірки з парами не спрацювали, просто переміщуємо тейл у вільну комірку
            # Пріоритет: 0, потім 1, а якщо третя розблокована – 2
            print(f"DEBUG tile_clicked solitaire2: Переміщую тейл у комірку. Перевіряю комірки: slot0={solitaire2_slots[0] is not None}, slot1={solitaire2_slots[1] is not None}, slot2={solitaire2_slots[2] is not None}, third_unlocked={solitaire2_third_slot_unlocked}")
            slot_index = None
            if solitaire2_slots[0] is None:
                print("DEBUG tile_clicked solitaire2: Переміщую тейл у верхню комірку (0)")
                slot_index = 0
                solitaire2_slots[0] = tile
                tile.removed = True  # Прибираємо з поля (не відображається на полі, але зберігається в комірці)
            elif solitaire2_slots[1] is None:
                print("DEBUG tile_clicked solitaire2: Переміщую тейл у нижню комірку (1)")
                slot_index = 1
                solitaire2_slots[1] = tile
                tile.removed = True  # Прибираємо з поля
            elif solitaire2_third_slot_unlocked and solitaire2_slots[2] is None:
                print("DEBUG tile_clicked solitaire2: Переміщую тейл у третю комірку (2)")
                slot_index = 2
                solitaire2_slots[2] = tile
                tile.removed = True  # Прибираємо з поля
            else:
                # Усі доступні комірки зайняті - не можна додати новий тейл
                print("DEBUG tile_clicked solitaire2: Усі доступні комірки зайняті, але відповідності не знайдено")
                return
            
            # Зберігаємо останній хід для можливості відміни (тільки один хід)
            solitaire2_last_move = {
                "tile": tile,
                "x": tile.x,
                "y": tile.y,
                "z": tile.z,
                "slot_index": slot_index
            }
            
            # ВАЖЛИВО: Спочатку оновлюємо UI, щоб тейл відобразився в комірці
            update_board()
            page.update()
            
            # Перевіряємо, чи в обох комірках тейли однакові ТІЛЬКИ після того, як тейл поміщено в другу комірку
            # Якщо так - чекаємо 0.3 секунди перед видаленням
            print(f"DEBUG tile_clicked solitaire2: Перевіряю на однаковість після поміщення тейла: slot0={solitaire2_slots[0] is not None}, slot1={solitaire2_slots[1] is not None}")
            
            # Перевірка відбувається тільки якщо обидві комірки заповнені (тобто тейл щойно поміщено в другу комірку)
            if solitaire2_slots[0] is not None and solitaire2_slots[1] is not None:
                print(f"DEBUG tile_clicked solitaire2: Обидві комірки заповнені, порівнюю типи: slot0.tile_type={solitaire2_slots[0].tile_type}, slot1.tile_type={solitaire2_slots[1].tile_type}")
                print(f"DEBUG tile_clicked solitaire2: Порівняння: {solitaire2_slots[0].tile_type == solitaire2_slots[1].tile_type}")
                if solitaire2_slots[0].tile_type == solitaire2_slots[1].tile_type:
                    # Однакові тейли - ВАЖЛИВО: тейл вже в комірці, тепер чекаємо 0.3 секунди перед видаленням
                    solitaire2_pending_removal = True
                    print(f"DEBUG tile_clicked solitaire2: Знайдено однакові тейли в комірках, чекаю 0.3 секунди перед видаленням")
                    
                    # Функція для видалення однакових тейлів після затримки
                    def remove_matching_tiles():
                        nonlocal solitaire2_slots, solitaire2_last_move, solitaire2_pending_removal
                        print(f"DEBUG remove_matching_tiles: Затримка 0.3 секунди завершена, перевіряю тейли перед видаленням")
                        if solitaire2_pending_removal and solitaire2_slots[0] is not None and solitaire2_slots[1] is not None:
                            if solitaire2_slots[0].tile_type == solitaire2_slots[1].tile_type:
                                print(f"DEBUG remove_matching_tiles: Видаляю однакові тейли")
                                # Однакові тейли - видаляємо обидва
                                solitaire2_pending_removal = False
                                solitaire2_last_move = None
                                # Позначаємо тейли як видалені
                                if solitaire2_slots[0]:
                                    solitaire2_slots[0].removed = True
                                if solitaire2_slots[1]:
                                    solitaire2_slots[1].removed = True
                                solitaire2_slots[0] = None
                                solitaire2_slots[1] = None
                                # Оновлюємо UI через page.run_task (async функція)
                                async def update_ui():
                                    update_board()
                                    page.update()
                                    check_game_state()
                                page.run_task(update_ui)
                            else:
                                print(f"DEBUG remove_matching_tiles: Тейли вже не однакові, не видаляю")
                                solitaire2_pending_removal = False
                        else:
                            print(f"DEBUG remove_matching_tiles: Прапор не встановлений або одна з комірок порожня, не видаляю")
                            solitaire2_pending_removal = False
                    
                    # Запускаємо через threading.Timer (0.3 секунди) - затримка перед видаленням
                    # Тейл вже в комірці і відображається, тому затримка гарантує, що він буде видимий перед видаленням
                    timer = threading.Timer(0.3, remove_matching_tiles)
                    timer.start()
                    print(f"DEBUG tile_clicked solitaire2: Запущено таймер на 0.3 секунди для видалення однакових тейлів")
                    return  # Виходимо, не викликаючи check_game_state зараз
            else:
                # Якщо тільки одна комірка заповнена - просто виходимо
                print(f"DEBUG tile_clicked solitaire2: Тільки одна комірка заповнена, перевірка на однаковість не потрібна")
            
            # Перевіряємо стан гри (включаючи перевірку на відсутність ходів)
            check_game_state()
            return
        
        # Для Пасьянс 1 та інших режимів - стандартна логіка
        if game_mode == "solitaire1":
            # Для solitaire1 використовуємо стандартну логіку через board.click_tile
            board.click_tile(tile)
            update_board()
        else:
            # Для інших режимів (якщо не solitaire2)
            board.clear_highlights()
            selected_before = board.selected_tile
            board.click_tile(tile)
            update_board()
    
    def undo_last_move_solitaire2():
        """Відміняє останній хід в Пасьянс-2"""
        nonlocal solitaire2_last_move, solitaire2_slots
        
        if solitaire2_last_move is None:
            # Немає ходу для відміни
            return
        
        # Відновлюємо тейл на попереднє місце
        tile = solitaire2_last_move["tile"]
        slot_index = solitaire2_last_move["slot_index"]
        
        # Перевіряємо, чи тейл все ще в комірці
        if solitaire2_slots[slot_index] != tile:
            # Тейл вже не в комірці (можливо, був видалений разом з іншим)
            solitaire2_last_move = None
            return
        
        # Повертаємо тейл на поле
        tile.x = solitaire2_last_move["x"]
        tile.y = solitaire2_last_move["y"]
        tile.z = solitaire2_last_move["z"]
        tile.removed = False
        
        # Очищаємо комірку
        solitaire2_slots[slot_index] = None
        
        # Очищаємо історію (можна відмінити тільки один хід)
        solitaire2_last_move = None
        
        update_board()
        page.update()
        # Перевіряємо, чи немає ходів після відміни
        check_game_state()
    
    def toggle_darken_mode():
        """Перемикає глобальний режим затемнення закритих тейлів"""
        nonlocal darken_mode
        darken_mode = not darken_mode
        update_board()
        page.update()
    
    start_button: Optional[ft.ElevatedButton]
    solitaire2_button: Optional[ft.ElevatedButton]
    duel_button: Optional[ft.ElevatedButton]

    def initialize_start_button():
        nonlocal start_button, solitaire1_pattern_dropdown, selected_solitaire1_pattern
        
        # Завантажуємо список патернів для solitaire1
        patterns_dir = Path("patterns")
        pattern_names = []
        if patterns_dir.exists():
            pattern_files = sorted(patterns_dir.glob("*.json"))
            for pattern_file in pattern_files:
                try:
                    with open(pattern_file, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    # Фільтруємо тільки патерни для solitaire1
                    pattern_game_mode = pattern_data.get("game_mode", "solitaire1")  # За замовчуванням solitaire1 для старих патернів
                    if pattern_game_mode == "solitaire1":
                        pattern_names.append(pattern_data.get("name", pattern_file.stem))
                except:
                    pass  # Пропускаємо файли з помилками
        
        # Створюємо випадаюче меню для вибору патерну
        solitaire1_pattern_dropdown = ft.Dropdown(
            label="Виберіть патерн",
            width=200,
            options=[ft.dropdown.Option(name) for name in pattern_names] if pattern_names else [],
            value=None,
        )
        
        # Обробник зміни вибору патерну
        def on_pattern_selected(e):
            nonlocal selected_solitaire1_pattern
            selected_solitaire1_pattern = solitaire1_pattern_dropdown.value
            # При зміні патерну одразу оновлюємо кращий час для нього
            refresh_profile_stats()
        
        solitaire1_pattern_dropdown.on_change = on_pattern_selected
        
        start_button = ft.ElevatedButton(
            "Пасьянс 1",
            width=220,
            height=40,
            on_click=lambda e: load_tiles(),
        )
        # Кнопка не видима до входу користувача
        start_button.visible = False
        if solitaire1_pattern_dropdown:
            solitaire1_pattern_dropdown.visible = False
    
    def refresh_solitaire1_dropdown():
        """Оновлює список патернів у випадаючому меню для solitaire1 (тільки патерни для solitaire1)"""
        nonlocal solitaire1_pattern_dropdown, selected_solitaire1_pattern
        if not solitaire1_pattern_dropdown:
            return
        
        patterns_dir = Path("patterns")
        pattern_names = []
        if patterns_dir.exists():
            pattern_files = sorted(patterns_dir.glob("*.json"))
            for pattern_file in pattern_files:
                try:
                    with open(pattern_file, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    # Фільтруємо тільки патерни для solitaire1
                    # За замовчуванням старі патерни вважаємо для Пасьянсу 2, тому вони не потрапляють у Пасьянс 1
                    pattern_game_mode = pattern_data.get("game_mode", "solitaire2")
                    # Нормалізуємо можливі старі текстові значення
                    if pattern_game_mode in ("Пасьянс 1", "solitaire1"):
                        pattern_game_mode = "solitaire1"
                    elif pattern_game_mode in ("Пасьянс 2", "solitaire2"):
                        pattern_game_mode = "solitaire2"
                    if pattern_game_mode == "solitaire1":
                        pattern_names.append(pattern_data.get("name", pattern_file.stem))
                except:
                    pass  # Пропускаємо файли з помилками
        
        solitaire1_pattern_dropdown.options = [ft.dropdown.Option(name) for name in pattern_names] if pattern_names else []
        # Зберігаємо вибране значення, якщо воно все ще існує
        if selected_solitaire1_pattern and selected_solitaire1_pattern in pattern_names:
            solitaire1_pattern_dropdown.value = selected_solitaire1_pattern
        else:
            solitaire1_pattern_dropdown.value = None
            selected_solitaire1_pattern = None
    
    def refresh_solitaire2_dropdown():
        """Оновлює список патернів у випадаючому меню для solitaire2 (тільки патерни для solitaire2)"""
        nonlocal solitaire2_pattern_dropdown, selected_solitaire2_pattern
        if not solitaire2_pattern_dropdown:
            return
        
        patterns_dir = Path("patterns")
        pattern_names = []
        if patterns_dir.exists():
            pattern_files = sorted(patterns_dir.glob("*.json"))
            for pattern_file in pattern_files:
                try:
                    with open(pattern_file, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    # Фільтруємо тільки патерни для solitaire2
                    # За замовчуванням старі патерни вважаємо для Пасьянсу 2
                    pattern_game_mode = pattern_data.get("game_mode", "solitaire2")
                    # Нормалізуємо можливі старі текстові значення
                    if pattern_game_mode in ("Пасьянс 1", "solitaire1"):
                        pattern_game_mode = "solitaire1"
                    elif pattern_game_mode in ("Пасьянс 2", "solitaire2"):
                        pattern_game_mode = "solitaire2"
                    if pattern_game_mode == "solitaire2":
                        pattern_names.append(pattern_data.get("name", pattern_file.stem))
                except:
                    pass  # Пропускаємо файли з помилками
        
        solitaire2_pattern_dropdown.options = [ft.dropdown.Option(name) for name in pattern_names] if pattern_names else []
        # Зберігаємо вибране значення, якщо воно все ще існує
        if selected_solitaire2_pattern and selected_solitaire2_pattern in pattern_names:
            solitaire2_pattern_dropdown.value = selected_solitaire2_pattern
        else:
            solitaire2_pattern_dropdown.value = None
            selected_solitaire2_pattern = None
    
    def initialize_solitaire2_button():
        nonlocal solitaire2_button, solitaire2_pattern_dropdown, selected_solitaire2_pattern
        
        # Завантажуємо список патернів
        patterns_dir = Path("patterns")
        pattern_names = []
        if patterns_dir.exists():
            pattern_files = sorted(patterns_dir.glob("*.json"))
            for pattern_file in pattern_files:
                try:
                    with open(pattern_file, "r", encoding="utf-8") as f:
                        pattern_data = json.load(f)
                    pattern_names.append(pattern_data.get("name", pattern_file.stem))
                except:
                    pattern_names.append(pattern_file.stem)
        
        # Створюємо випадаюче меню для вибору патерну
        solitaire2_pattern_dropdown = ft.Dropdown(
            label="Виберіть патерн",
            width=200,
            options=[ft.dropdown.Option(name) for name in pattern_names] if pattern_names else [],
            value=None,
        )
        
        # Обробник зміни вибору патерну
        def on_pattern_selected(e):
            nonlocal selected_solitaire2_pattern
            selected_solitaire2_pattern = solitaire2_pattern_dropdown.value
            # При зміні патерну одразу оновлюємо кращий час для нього
            refresh_profile_stats()
        
        solitaire2_pattern_dropdown.on_change = on_pattern_selected
        
        solitaire2_button = ft.ElevatedButton(
            "Пасьянс 2",
            width=220,
            height=40,
            on_click=lambda e: start_solitaire2_mode(solitaire2_pattern_dropdown.value if solitaire2_pattern_dropdown else selected_solitaire2_pattern),
        )
        # Кнопка не видима до входу користувача
        solitaire2_button.visible = False
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = False
    
    def start_solitaire2_mode(pattern_name: Optional[str] = None):
        """Запускає режим Пасьянс 2 з вибраним патерном"""
        nonlocal solitaire2_button, solitaire2_pattern_dropdown, current_session_id, solitaire2_slots, board, pattern_constructor_mode
        nonlocal hints_remaining, shuffle_remaining, timer_started, elapsed_seconds, start_time, selected_solitaire2_pattern
        nonlocal solitaire2_third_slot_unlocked
        nonlocal finish_text_container
        global game_mode, current_pattern_name
        game_mode = "solitaire2"
        pattern_constructor_mode = False  # Скидаємо режим конструктора
        solitaire2_slots = [None, None, None]
        solitaire2_third_slot_unlocked = False  # Третя комірка на початку кожної гри заблокована
        solitaire2_last_move = None  # Очищаємо слоти
        # Приховуємо напис фінішу при виборі нового режиму
        if finish_text_container:
            finish_text_container.visible = False
        
        # Використовуємо вибраний патерн з меню, якщо не вказано явно
        if not pattern_name:
            # Спочатку перевіряємо поточне значення в dropdown
            if solitaire2_pattern_dropdown and solitaire2_pattern_dropdown.value:
                pattern_name = solitaire2_pattern_dropdown.value
            # Якщо в dropdown немає, використовуємо збережене значення
            elif selected_solitaire2_pattern:
                pattern_name = selected_solitaire2_pattern
        
        print(f"DEBUG start_solitaire2_mode: pattern_name={pattern_name}, dropdown.value={solitaire2_pattern_dropdown.value if solitaire2_pattern_dropdown else None}, selected_solitaire2_pattern={selected_solitaire2_pattern}")
        
        # Приховуємо кнопки режимів
        if solitaire2_button:
            solitaire2_button.visible = False
        if solitaire2_pattern_dropdown:
            solitaire2_pattern_dropdown.visible = False
        if start_button:
            start_button.visible = False
        if duel_button:
            duel_button.visible = False
        if duel2_button:
            duel2_button.visible = False
        
        # Створюємо нову дошку з правильним game_mode
        timer_control.stop()
        # ВАЖЛИВО: Передаємо pattern_name в конструктор Board, щоб він був доступний при виклику generate_board()
        board = Board(pattern_name=pattern_name)  # Створюємо нову дошку з game_mode="solitaire2" та вибраним патерном
        # Запам'ятовуємо патерн, з яким запущена гра
        current_pattern_name = pattern_name
        print(f"DEBUG start_solitaire2_mode: Створено Board з pattern_name={pattern_name}, board.selected_pattern_name={board.selected_pattern_name}")
        # На початку будь-якої гри завжди 2 підказки і 1 тасування (базові)
        # Додаємо додаткові куплені підказки/тасування з бази даних
        hints_remaining = 2
        shuffle_remaining = 1
        if current_profile["id"] is not None:
            hints_remaining += get_user_hints(current_profile["id"])
            shuffle_remaining += get_user_shuffles(current_profile["id"])
        timer_started = False
        elapsed_seconds = 0
        start_time = 0.0
        timer_text.value = format_duration(0)
        pause_overlay.visible = False
        pause_overlay.opacity = 0
        # Приховуємо напис фінішу при старті нової гри
        if finish_text_container:
            finish_text_container.visible = False
        board_container.opacity = 1
        
        # Запускаємо гру
        if current_profile["id"] and current_session_id is None:
            current_session_id = start_session(current_profile["id"])
        start_timer(reset=True)
        update_action_ui()
        update_board()
        page.snack_bar = ft.SnackBar(ft.Text("Режим Пасьянс 2 розпочато"), open=True)
        page.update()
    
    def initialize_duel_button():
        nonlocal duel_button
        duel_button = ft.ElevatedButton(
            "Дуель 1",
            width=220,
            height=40,
            on_click=lambda e: start_duel_mode(),
        )
        # Кнопка не видима до входу користувача
        duel_button.visible = False
    
    def initialize_duel2_button():
        nonlocal duel2_button
        duel2_button = ft.ElevatedButton(
            "Дуель 2",
            width=220,
            height=40,
            on_click=lambda e: start_duel2_mode(),
        )
        # Кнопка не видима до входу користувача
        duel2_button.visible = False
    
    def start_duel_mode():
        """Заглушка для режиму дуелі (буде реалізовано пізніше)"""
        nonlocal pattern_constructor_mode
        pattern_constructor_mode = False  # Скидаємо режим конструктора
        page.snack_bar = ft.SnackBar(ft.Text("Режим дуелі буде реалізовано"), open=True)
        page.update()
    
    def start_duel2_mode():
        """Заглушка для режиму дуелі 2 (буде реалізовано пізніше)"""
        nonlocal pattern_constructor_mode
        pattern_constructor_mode = False  # Скидаємо режим конструктора
        page.snack_bar = ft.SnackBar(ft.Text("Режим дуелі 2 буде реалізовано"), open=True)
        page.update()

    def load_tiles():
        nonlocal start_button, solitaire2_button, duel_button, duel2_button, current_session_id, solitaire2_slots, board, pattern_constructor_mode, finish_text_container
        nonlocal solitaire1_pattern_dropdown, selected_solitaire1_pattern
        global game_mode
        game_mode = "solitaire1"
        pattern_constructor_mode = False  # Скидаємо режим конструктора
        solitaire2_slots = [None, None, None]
        solitaire2_last_move = None  # Очищаємо слоти
        # Приховуємо напис фінішу при виборі нового режиму
        if finish_text_container:
            finish_text_container.visible = False
        
        # Запускаємо гру з вибраним патерном
        pattern_name = solitaire1_pattern_dropdown.value if solitaire1_pattern_dropdown else selected_solitaire1_pattern
        start_new_game(pattern_name=pattern_name)
    
    def update_board():
        """Оновлює відображення дошки"""
        global game_mode
        nonlocal main_stack, sidebar_slots_area, tile_palette_container, solitaire2_last_move, darken_mode
        print(f"DEBUG update_board: current_profile['id']={current_profile['id']}")
        print(f"DEBUG update_board: start_button={start_button}, start_button.visible={start_button.visible if start_button else 'None'}")
        print(f"DEBUG update_board: duel_button={duel_button}, duel_button.visible={duel_button.visible if duel_button else 'None'}")
        print(f"DEBUG update_board: board.game_over={board.game_over if board else 'None'}")
        board_container.controls.clear()
        # Очищаємо панель тейлів, якщо конструктор не активний
        if not pattern_constructor_mode:
            tile_palette_container.controls.clear()
        
        # Якщо користувач увійшов, але гра ще не почалася - показуємо кнопки режимів в верхньому лівому куті
        if current_profile["id"] is not None and start_button and start_button.visible:
            print(f"DEBUG update_board: Показую рамочки з режимами")
            # Заголовок для однокористувацького режиму
            single_player_title = ft.Container(
                content=ft.Text(
                    "Однокористувацький режим",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=TEXT_COLOR,
                ),
                left=10,
                top=10,
            )
            board_container.controls.append(single_player_title)
            
            # Рамочка для однокористувацького режиму (місце для кнопок та меню)
            # Додаємо кнопки в список
            single_player_buttons = []
            
            # Кнопка "Пасьянс 1" з меню
            if start_button:
                single_player_buttons.append(start_button)
                if solitaire1_pattern_dropdown:
                    # Переконуємося, що меню видиме
                    solitaire1_pattern_dropdown.visible = True
                    # Вирівнюємо меню по центру рамочки
                    dropdown_wrapper = ft.Container(
                        content=solitaire1_pattern_dropdown,
                        margin=ft.margin.only(left=10),  # Зсув вправо на 10px для центрування
                    )
                    single_player_buttons.append(dropdown_wrapper)
            
            # Кнопка "Пасьянс 2" з меню
            if solitaire2_button and solitaire2_button.visible:
                # Спочатку додаємо кнопку, потім випадаюче меню
                single_player_buttons.append(solitaire2_button)
                if solitaire2_pattern_dropdown:
                    # Переконуємося, що меню видиме
                    solitaire2_pattern_dropdown.visible = True
                    # Вирівнюємо меню по центру рамочки
                    dropdown_wrapper = ft.Container(
                        content=solitaire2_pattern_dropdown,
                        margin=ft.margin.only(left=10),  # Зсув вправо на 10px для центрування
                    )
                    single_player_buttons.append(dropdown_wrapper)
            
            # Розраховуємо висоту рамочки в залежності від кількості елементів
            # Кожна кнопка (40px) + меню (~50px) + spacing (10px) = ~100px на пару кнопка+меню
            # Якщо тільки кнопки без меню, то ~50px на кнопку
            frame_height = len(single_player_buttons) * 50 + 30  # 50px на елемент + 20px padding + 10px додатково
            
            single_player_frame = ft.Container(
                content=ft.Column(
                    controls=single_player_buttons,
                    spacing=10,  # Відступ між кнопками
                ),
                width=240,  # 220 (ширина кнопки) + 20 (відступи)
                height=frame_height,  # Динамічна висота
                border=ft.border.all(1, "#000000"),  # Чорна тонка рамка
                border_radius=5,
                padding=ft.padding.all(10),
                bgcolor=None,  # Прозорий фон
                left=10,
                top=40,  # 10 (відступ зверху) + 30 (висота заголовка)
            )
            board_container.controls.append(single_player_frame)
            
            # Рамочка для багатокористувацького режиму
            if (duel_button and duel_button.visible) or (duel2_button and duel2_button.visible):
                # Заголовок для багатокористувацького режиму
                multiplayer_title = ft.Container(
                    content=ft.Text(
                        "Багатокористувацький режим",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_COLOR,
                    ),
                    left=10,
                    top=280,  # 10 (відступ зверху) + 40 (заголовок) + 210 (висота першої рамочки збільшена) + 20 (відступ між заголовками)
                )
                board_container.controls.append(multiplayer_title)
                
                # Додаємо кнопки в список
                multiplayer_buttons = []
                if duel_button and duel_button.visible:
                    multiplayer_buttons.append(duel_button)
                if duel2_button and duel2_button.visible:
                    # Додаємо контейнер з відступом зверху для кнопки "Дуель-2"
                    duel2_wrapper = ft.Container(
                        content=duel2_button,
                        margin=ft.margin.only(top=-4),  # Піднімаємо на 4 пікселі вгору
                    )
                    multiplayer_buttons.append(duel2_wrapper)
                
                multiplayer_frame = ft.Container(
                    content=ft.Column(
                        controls=multiplayer_buttons,
                        spacing=10,  # Відступ між кнопками
                    ),
                    width=240,  # 220 (ширина кнопки) + 20 (відступи)
                    height=110 if len(multiplayer_buttons) > 1 else 80,  # 2 кнопки по 40px + відступи або 1 кнопка (збільшено на 10px)
                    border=ft.border.all(1, "#000000"),  # Чорна тонка рамка
                    border_radius=5,
                    padding=ft.padding.all(10),
                    bgcolor=None,  # Прозорий фон
                    left=10,
                    top=310,  # 10 (відступ зверху) + 40 (заголовок) + 210 (висота першої рамочки збільшена) + 50 (відступ між рамочками)
                )
                board_container.controls.append(multiplayer_frame)
            
            # Кнопка "Конструктор патернів" під рамочками
            pattern_constructor_button = ft.ElevatedButton(
                "Конструктор патернів",
                width=240,
                height=40,
                bgcolor="#9C27B0",  # Фіолетовий колір
                color="#FFFFFF",
                on_click=lambda e: open_pattern_constructor(),
            )
            # Розраховуємо позицію в залежності від того, чи є багатокористувацький режим
            has_multiplayer = (duel_button and duel_button.visible) or (duel2_button and duel2_button.visible)
            multiplayer_height = 110 if ((duel_button and duel_button.visible) and (duel2_button and duel2_button.visible)) else 80
            constructor_top = 310 + multiplayer_height + 20 if has_multiplayer else 290  # Під рамочкою багатокористувацького режиму або під однокористувацьким (з урахуванням збільшеної рамочки)
            pattern_constructor_frame = ft.Container(
                content=pattern_constructor_button,
                left=10,
                top=constructor_top,  # Під рамочками режимів з відступом
            )
            board_container.controls.append(pattern_constructor_frame)
        # Якщо конструктор патернів активний
        elif pattern_constructor_mode:
            # Очищаємо комірки в прозорій зоні сайдбару для конструктора
            if sidebar_slots_area.content is None or not isinstance(sidebar_slots_area.content, ft.Stack):
                sidebar_slots_area.content = ft.Stack([])
            else:
                sidebar_slots_area.content.controls.clear()
            # Показуємо поле конструктора
            render_pattern_constructor()
        # Якщо гра активна - показуємо плитки
        elif current_profile["id"] is not None:
            # Показуємо основні плитки
            # Сортуємо за z (рівень), потім y, потім x - тейли з більшим z будуть зверху
            for tile in sorted(board.tiles, key=lambda t: (t.z, t.y, t.x)):
                if not tile.removed:
                    tile_container = create_tile_container(tile)
                    # Всі тейли мають повну непрозорість (opacity=1.0 вже встановлено в create_tile_container)
                    board_container.controls.append(tile_container)
            
            # Якщо режим "Пасьянс 2" - додаємо три рамочки внизу справа (2 пусті + 1 заблокована)
            # Якщо режим "Пасьянс 2" - додаємо три рамочки в прозорій частині сайдбару (2 пусті + 1 заблокована)
            if game_mode == "solitaire2":
                # Очищаємо старі комірки з прозорої частини сайдбару
                if sidebar_slots_area.content is None or not isinstance(sidebar_slots_area.content, ft.Stack):
                    sidebar_slots_area.content = ft.Stack([])
                else:
                    sidebar_slots_area.content.controls.clear()
                # Знаходимо максимальні координати серед усіх тейлів
                max_x = 0
                max_y = 0
                for tile in board.tiles:
                    if not tile.removed:
                        # Враховуємо зміщення для Пасьянс 2 (z-координата) при обчисленні позиції на екрані
                        # Зміщення для шарів: трохи вгору і вправо для вищих рівнів
                        z_offset_x = tile.z * 5 if game_mode == "solitaire2" else 0  # Зміщення вправо для вищих рівнів (5px на шар)
                        z_offset_y = -tile.z * 5 if game_mode == "solitaire2" else 0  # Зміщення вгору для вищих рівнів (5px на шар)
                        tile_screen_x = 10 + tile.x * TILE_SPACING_X + z_offset_x
                        tile_screen_y = 10 + tile.y * TILE_SPACING_Y + z_offset_y  # Глобальний відступ зверху = 10
                        if tile_screen_x > max_x:
                            max_x = tile_screen_x
                        if tile_screen_y > max_y:
                            max_y = tile_screen_y
                
                # Розташовуємо рамочки всередині прозорої частини сайдбару (60px зліва)
                # Комірки будуть рухатися разом з сайдбаром при зміні розміру вікна
                # Комірки по лівому краю прозорої частини
                slot_x = 0  # Позиція на лівому краю прозорої частини (60px достатньо для комірок шириною 50px)
                
                slot_spacing = 1  # Мінімальний відступ між рамочками (1 піксель)
                # Розміщуємо комірки внизу контейнера sidebar_slots_area (висота = 730)
                # 3 комірки по 70px висоти + 2 відступи по 1px = 212px загалом
                slot_y_start = 730 - 3 * TILE_HEIGHT - 2 * slot_spacing  # Внизу контейнера
                
                # Не перевіряємо межі board_container, бо комірки мають бути на фіксованій позиції відносно сайдбару
                
                print(f"DEBUG solitaire2_slots: slot_x={slot_x}, slot_y_start={slot_y_start}, max_x={max_x}, max_y={max_y}, offset_right={SOLITAIRE2_SLOTS_OFFSET_RIGHT}")
                
                # Створюємо три рамочки
                for i in range(3):
                    slot_y = slot_y_start + i * (TILE_HEIGHT + slot_spacing)
                    
                    if i < 2:
                        # Перші дві - рамочки з тейлами або порожні
                        slot_tile = solitaire2_slots[i]
                        if slot_tile is not None:
                            # У комірці є тейл - відображаємо його (без можливості кліку)
                            # Створюємо контейнер для тейла в комірці
                            if slot_tile.tile_type in tile_images:
                                tile_content = ft.Image(
                                    src=tile_images[slot_tile.tile_type],
                                    width=TILE_WIDTH,
                                    height=TILE_HEIGHT,
                                    fit=ft.ImageFit.CONTAIN,
                                )
                            else:
                                tile_content = ft.Container(
                                    content=ft.Text(
                                        slot_tile.get_display_name(),
                                        size=16,
                                        color="#000000",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    alignment=ft.alignment.center,
                                    width=TILE_WIDTH,
                                    height=TILE_HEIGHT,
                                    bgcolor=TILE_COLOR,
                                )
                            
                            slot_tile_container = ft.Container(
                                content=tile_content,
                                left=slot_x,
                                top=slot_y,
                                width=TILE_WIDTH,
                                height=TILE_HEIGHT,
                                border=ft.border.all(1, "#888888"),
                                border_radius=5,
                                shadow=ft.BoxShadow(
                                    spread_radius=1,
                                    blur_radius=8,
                                    color="#00000066",
                                    offset=ft.Offset(2, 3),
                                ),
                                opacity=1.0,
                                # Без on_click - тейли в комірках не клікабельні
                            )
                            sidebar_slots_area.content.controls.append(slot_tile_container)
                        else:
                            # Порожня рамочка
                            empty_slot = ft.Container(
                                width=TILE_WIDTH,
                                height=TILE_HEIGHT,
                                left=slot_x,
                                top=slot_y,
                                border=ft.border.all(2, "#888888"),  # Сіра рамка
                                border_radius=5,
                                bgcolor="#2A2A2A",  # Темний фон для порожнього слота
                                content=ft.Container(
                                    content=ft.Text("", size=12, color="#666666"),
                                    alignment=ft.alignment.center,
                                ),
                            )
                            sidebar_slots_area.content.controls.append(empty_slot)
                    else:
                        # Третя комірка: може бути заблокована або активна (якщо розблокована за coins)
                        if solitaire2_third_slot_unlocked:
                            # Активна третя комірка працює як додатковий буфер (без логіки видалення пар)
                            slot_tile = solitaire2_slots[2]
                            if slot_tile is not None:
                                if slot_tile.tile_type in tile_images:
                                    tile_content = ft.Image(
                                        src=tile_images[slot_tile.tile_type],
                                        width=TILE_WIDTH,
                                        height=TILE_HEIGHT,
                                        fit=ft.ImageFit.CONTAIN,
                                    )
                                else:
                                    tile_content = ft.Container(
                                        content=ft.Text(
                                            slot_tile.get_display_name(),
                                            size=16,
                                            color="#000000",
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                        alignment=ft.alignment.center,
                                        width=TILE_WIDTH,
                                        height=TILE_HEIGHT,
                                        bgcolor=TILE_COLOR,
                                    )
                                slot_tile_container = ft.Container(
                                    content=tile_content,
                                    left=slot_x,
                                    top=slot_y,
                                    width=TILE_WIDTH,
                                    height=TILE_HEIGHT,
                                    border=ft.border.all(1, "#888888"),
                                    border_radius=5,
                                    shadow=ft.BoxShadow(
                                        spread_radius=1,
                                        blur_radius=8,
                                        color="#00000066",
                                        offset=ft.Offset(2, 3),
                                    ),
                                    opacity=1.0,
                                )
                                sidebar_slots_area.content.controls.append(slot_tile_container)
                            else:
                                # Порожня активна третя комірка
                                empty_slot = ft.Container(
                                    width=TILE_WIDTH,
                                    height=TILE_HEIGHT,
                                    left=slot_x,
                                    top=slot_y,
                                    border=ft.border.all(2, "#FFD700"),  # Золота рамка для розблокованої
                                    border_radius=5,
                                    bgcolor="#2A2A2A",
                                    content=ft.Container(
                                        content=ft.Text("", size=12, color="#AAAA44"),
                                        alignment=ft.alignment.center,
                                    ),
                                )
                                sidebar_slots_area.content.controls.append(empty_slot)
                        else:
                            # Третя - заблокована з замочком, можна розблокувати за 2 coins
                            def unlock_third_slot(e):
                                nonlocal solitaire2_third_slot_unlocked
                                if solitaire2_third_slot_unlocked:
                                    return
                                if current_profile["id"] is None:
                                    page.snack_bar = ft.SnackBar(ft.Text("Увійдіть, щоб розблокувати третю комірку"), open=True)
                                    page.update()
                                    return
                                coins = get_user_coins(current_profile["id"])
                                if coins < 2:
                                    page.snack_bar = ft.SnackBar(ft.Text("Недостатньо монет (потрібно 2 coins)"), open=True)
                                    page.update()
                                    return
                                # Знімаємо 2 coins та розблоковуємо третю комірку для поточної гри
                                update_user_coins(current_profile["id"], coins - 2)
                                solitaire2_third_slot_unlocked = True
                                # Оновлюємо sidebar (coins) та перерисовуємо слоти
                                update_sidebar()
                                update_board()
                            
                            locked_slot = ft.Container(
                                width=TILE_WIDTH,
                                height=TILE_HEIGHT,
                                left=slot_x,
                                top=slot_y,
                                border=ft.border.all(2, "#666666"),  # Темніша рамка для заблокованого
                                border_radius=5,
                                bgcolor="#1A1A1A",  # Ще темніший фон
                                content=ft.Container(
                                    content=ft.Icon(
                                        name="lock",
                                        size=24,
                                        color="#666666",
                                    ),
                                    alignment=ft.alignment.center,
                                ),
                                on_click=unlock_third_slot,
                                tooltip="Розблокувати третю комірку за 2 coins",
                            )
                            # Додаємо до прозорої частини сайдбару
                            sidebar_slots_area.content.controls.append(locked_slot)
                            continue
                
                # Створюємо кнопку перемикання режиму затемнення над кнопкою undo
                # slot_y_start - це Y координата першої комірки, відступаємо на 174px вгору
                darken_button_y = slot_y_start - 172
                darken_button = ft.Container(
                    content=ft.IconButton(
                        icon="visibility" if darken_mode else "visibility_off",
                        icon_size=32,
                        icon_color=TEXT_COLOR if darken_mode else "#666666",
                        tooltip="Вимкнути затемнення" if darken_mode else "Увімкнути затемнення",
                        on_click=lambda e: toggle_darken_mode(),
                    ),
                    left=slot_x,
                    top=darken_button_y,
                    width=TILE_WIDTH,
                    height=TILE_HEIGHT,
                    border=ft.border.all(2, "#888888" if darken_mode else "#666666"),
                    border_radius=5,
                    bgcolor="#2A2A2A",
                    alignment=ft.alignment.center,
                )
                sidebar_slots_area.content.controls.append(darken_button)
                
                # Створюємо кнопку "відмінити хід" над комірками (після створення комірок)
                # slot_y_start - це Y координата першої комірки, відступаємо на 100px вгору
                undo_button_y = slot_y_start - 100
                undo_button = ft.Container(
                    content=ft.IconButton(
                        icon="undo",
                        icon_size=32,
                        icon_color=TEXT_COLOR if solitaire2_last_move is not None else "#666666",  # Сірий, якщо немає ходу для відміни
                        tooltip="Відмінити хід",
                        disabled=solitaire2_last_move is None,  # Неактивна, якщо немає ходу для відміни
                        on_click=lambda e: undo_last_move_solitaire2(),
                    ),
                    left=slot_x,
                    top=undo_button_y,
                    width=TILE_WIDTH,
                    height=TILE_HEIGHT,
                    border=ft.border.all(2, "#888888" if solitaire2_last_move is not None else "#666666"),  # Рамка як у комірки
                    border_radius=5,
                    bgcolor="#2A2A2A",  # Темний фон як у комірки
                    alignment=ft.alignment.center,  # Центруємо іконку
                )
                sidebar_slots_area.content.controls.append(undo_button)
            else:
                # Для Пасьянс 1 комірки не потрібні - очищаємо їх
                if sidebar_slots_area.content is None or not isinstance(sidebar_slots_area.content, ft.Stack):
                    sidebar_slots_area.content = ft.Stack([])
                else:
                    sidebar_slots_area.content.controls.clear()
        
        # Додаємо overlay елементи (перевіряємо, чи вони ще не додані)
        if pause_overlay not in board_container.controls:
            board_container.controls.append(pause_overlay)
        # Додаємо напис фінішу, якщо він існує і ще не доданий
        if finish_text_container and finish_text_container not in board_container.controls:
            board_container.controls.append(finish_text_container)
        
        # Оновлюємо сторінку
        update_action_ui()
        page.update()
        # Панель інформації прибрано повністю
        check_game_state()

    initialize_start_button()
    initialize_duel_button()
    initialize_duel2_button()
    
    # Початкове оновлення sidebar (без таблиці рекордів, якщо користувач не увійшов)
    update_sidebar()
    
    # Початкове оновлення
    update_board()
    
    # Додаємо main_stack на сторінку
    page.add(main_stack)
    page.update()
    
    # Завжди показуємо діалог входу/реєстрації при старті
    # Заповнюємо поля збереженими даними, якщо вони є
    remembered = load_remembered_credentials()
    if remembered:
        login_username_field.value = remembered["username"]
        login_password_field.value = remembered["password"]
    
    # Показуємо діалог завжди
    show_auth_dialog()


if __name__ == "__main__":
    # Для веб-деплою на Render.com використовуємо WEB_BROWSER view
    # Для локального запуску можна використати ft.AppView.FLET_APP
    import os
    port = int(os.getenv("PORT", 8000))  # Render надає PORT автоматично
    if os.getenv("RENDER") or os.getenv("PORT"):
        # Запуск на Render.com або іншому хостингу
        ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=port, host="0.0.0.0")
    else:
        # Локальний запуск
        ft.app(target=main)

