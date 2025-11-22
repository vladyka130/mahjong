"""
Mahjong Solitaire Game на Flet
Класична гра-головоломка з плитками маджонгу
"""

import flet as ft
import json
import random
import threading
import time
import winsound
import sqlite3
import hashlib
import secrets
from pathlib import Path
from enum import Enum
from typing import Any, List, Tuple, Optional, Dict
from collections import deque
from datetime import datetime

# Константи
TILE_WIDTH = 50
TILE_HEIGHT = 70
TILE_SPACING_X = 51  # Щільно, але без накладання (ширина плитки 50px)
TILE_SPACING_Y = 71  # Щільно, але без накладання (висота плитки 70px)

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
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            duration INTEGER NOT NULL,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        )
        """
    )
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


def create_profile(username: str, password: str) -> Optional[Dict]:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    password_hash, salt = _hash_password(password)
    try:
        cursor.execute(
            "INSERT INTO profiles (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, salt, datetime.now().isoformat()),
        )
    except sqlite3.IntegrityError:
        conn.close()
        save_encrypted_db(db_path)
        return None
    profile_id = cursor.lastrowid
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)
    return {"id": profile_id, "username": username}


def authenticate(username: str, password: str) -> Optional[Dict]:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, salt FROM profiles WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    save_encrypted_db(db_path)
    if not row:
        return None
    profile_id, stored_hash, salt_hex = row
    candidate_hash, _ = _hash_password(password, bytes.fromhex(salt_hex))
    if candidate_hash != stored_hash:
        return None
    return {"id": profile_id, "username": username}


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


def insert_profile_record(profile_id: int, duration: int, timestamp: Optional[str] = None):
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO records (profile_id, timestamp, duration) VALUES (?, ?, ?)",
        (profile_id, timestamp, duration),
    )
    conn.commit()
    conn.close()
    save_encrypted_db(db_path)


def fetch_profile_stats(profile_id: int) -> Dict[str, Optional[int]]:
    db_path = load_encrypted_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*), MIN(duration), MAX(duration) FROM records WHERE profile_id = ?",
        (profile_id,),
    )
    row = cursor.fetchone()
    conn.close()
    save_encrypted_db(db_path)
    if not row:
        return {"games": 0, "best": None, "worst": None}
    games, best, worst = row
    return {"games": games or 0, "best": best, "worst": worst}


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
    
    def __init__(self):
        self.tiles: List[Tile] = []
        self.selected_tile: Optional[Tile] = None
        self.width = 20
        self.height = 10
        self.game_over = False
        self.basic_tile_types = [
            TileType.BAMBOO_1, TileType.BAMBOO_2, TileType.BAMBOO_3, TileType.BAMBOO_4,
            TileType.BAMBOO_5, TileType.BAMBOO_6, TileType.BAMBOO_7, TileType.BAMBOO_8, TileType.BAMBOO_9,
            TileType.DOT_1, TileType.DOT_2, TileType.DOT_3, TileType.DOT_4,
            TileType.DOT_5, TileType.DOT_6, TileType.DOT_7, TileType.DOT_8, TileType.DOT_9,
            TileType.WAN_1, TileType.WAN_2, TileType.WAN_3, TileType.WAN_4,
            TileType.WAN_5, TileType.WAN_6, TileType.WAN_7, TileType.WAN_8, TileType.WAN_9,
            TileType.EAST, TileType.SOUTH, TileType.WEST, TileType.NORTH,
            TileType.RED_DRAGON, TileType.GREEN_DRAGON, TileType.WHITE_DRAGON,
        ]
        self.generate_board()
        
    def generate_board(self):
        """Генерує дошку з плитками у вигляді патерну, повторюючи тасування поки є хід"""
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
        pattern = self._create_pyramid_pattern()
        
        tile_index = 0
        for z, layer in enumerate(pattern):
            for y, row in enumerate(layer):
                for x, has_tile in enumerate(row):
                        if has_tile and tile_index < len(board_tiles):
                            self.tiles.append(Tile(board_tiles[tile_index], x, y, z))
                        tile_index += 1

            if not self.is_game_lost():
                self.width = len(pattern[0][0])
                self.height = len(pattern[0])
                return

        print("WARNING: Не вдалося згенерувати дошку з ходом за", max_attempts, "спроб")
    
    def _create_pyramid_pattern(self) -> List[List[List[bool]]]:
        """Створює простий патерн 20x10 плиток"""
        # Простий прямокутник: 20 плиток по горизонталі, 10 по вертикалі
        layer0 = []
        
        # Створюємо 10 рядків по 20 плиток
        for y in range(10):
            row = [True] * 20  # 20 плиток у кожному рядку
            layer0.append(row)
        
        # Повертаємо один шар
        return [layer0]
    
    def is_tile_available(self, tile: Tile) -> bool:
        """Перевіряє, чи плитка доступна (немає плиток зверху + хоч один берег вільний/має пару)"""
        if tile.removed:
            return False
        
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
        if self.game_over:
            return
        if tile.removed:
            return
        
        if not self.is_tile_available(tile):
            if self.selected_tile:
                self.selected_tile.selected = False
                self.selected_tile = None
            return
        
        if self.selected_tile is None:
            self.selected_tile = tile
            tile.selected = True
        elif self.selected_tile is tile:
            self.selected_tile.selected = False
            self.selected_tile = None
        elif self.selected_tile.tile_type == tile.tile_type:
            if (
                self.is_tile_available(self.selected_tile)
                and self.is_tile_available(tile)
                and self.can_connect(self.selected_tile, tile)
            ):
                self.selected_tile.removed = True
                tile.removed = True
                self.selected_tile.selected = False
                self.selected_tile = None
            else:
                self.selected_tile.selected = False
                self.selected_tile = tile
                tile.selected = True
        else:
            self.selected_tile.selected = False
            self.selected_tile = tile
            tile.selected = True
    
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
    page.window.width = 1400
    page.window.height = 800  # Висота для 10 рядів: 50 (відступ) + 10*71 + 40 (відступ) = 800
    page.bgcolor = BACKGROUND_COLOR
    page.scroll = ft.ScrollMode.AUTO  # Додаємо прокрутку
    
    initialize_db()
    board = Board()
    
    # Завантаження зображень плиток
    tile_images = {}
    tiles_dir = Path("assets/tiles")
    
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
        
        for tile_type, possible_names in tile_file_mapping.items():
            for filename in possible_names:
                file_path = tiles_dir / filename
                if file_path.exists() or filename.lower() in existing_files:
                    if filename.lower() in existing_files:
                        file_path = existing_files[filename.lower()]
                    try:
                        tile_images[tile_type] = str(file_path)
                        break
                    except:
                        pass
    
    # UI елементи
    board_container = ft.Stack([], width=1100, height=800)
    hints_remaining = 2
    shuffle_remaining = 1
    game_records: List[dict] = []
    current_profile: Dict[str, Optional[Any]] = {"id": None, "username": None}
    profile_label = ft.Text("Гравець: (не вхід)", size=14, color=TEXT_COLOR)
    games_label = ft.Text("Ігор: 0", size=12, color="#CCCCCC")
    best_time_label = ft.Text("Найкращий час: --:--", size=12, color="#CCCCCC")
    current_session_id: Optional[int] = None
    start_button: Optional[ft.ElevatedButton] = None
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
        border=ft.border.all(1, "#888888"),
        divider_thickness=1,
        width=260,
        horizontal_lines=ft.border.BorderSide(1, "#888888"),
        vertical_lines=ft.border.BorderSide(1, "#888888"),
    )
    reshuffle_prompt_open = False
    reshuffle_dialog: Optional[ft.AlertDialog] = None
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
    results_overlay = ft.Container(
        expand=True,
        bgcolor="#222222",
        opacity=0,
        visible=False,
        alignment=ft.alignment.center,
        content=ft.Column([], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
    )
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
        try:
            winsound.PlaySound(sound_name, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except RuntimeError:
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
    login_password_field = ft.TextField(label="Пароль", password=True, can_reveal_password=True, width=250)
    login_confirm_field = ft.TextField(label="Підтвердження пароля", password=True, can_reveal_password=True, width=250, visible=False)
    auth_error_text = ft.Text("", size=12, color="#FF6B6B")
    auth_overlay_container: Optional[ft.Container] = None
    is_register_mode = False
    
    def handle_successful_login(profile: Dict[str, Any]):
        """Обробка успішного входу"""
        nonlocal current_profile, game_records, profile_label, auth_overlay_container
        current_profile["id"] = profile["id"]
        current_profile["username"] = profile["username"]
        profile_label.value = f"Гравець: {profile['username']}"
        game_records = fetch_profile_records(profile["id"])
        refresh_records_table()
        refresh_profile_stats()
        
        # Приховуємо overlay входу
        if auth_overlay_container:
            auth_overlay_container.visible = False
            if auth_overlay_container in page.overlay:
                page.overlay.remove(auth_overlay_container)
        
        # Ініціалізуємо кнопку старту
        if start_button is None:
            initialize_start_button()
        if start_button:
            start_button.visible = True
        
        refresh_leaderboard()
        refresh_profile_stats()
        update_board()
        page.update()
    
    def handle_login():
        """Обробка входу"""
        username = login_username_field.value.strip()
        password = login_password_field.value or ""
        
        if not username or not password:
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
            auth_error_text.value = "Невірні логін або пароль"
            page.update()
    
    def handle_register():
        """Обробка реєстрації"""
        username = login_username_field.value.strip()
        password = login_password_field.value or ""
        confirm = login_confirm_field.value or ""
        
        if not username or not password or not confirm:
            auth_error_text.value = "Заповни всі поля"
            page.update()
            return
        
        if password != confirm:
            auth_error_text.value = "Паролі не збігаються"
            page.update()
            return
        
        # Спробувати зареєструватися
        profile = create_profile(username, password)
        if profile:
            # Зберігаємо дані для автоматичного входу
            save_remembered_credentials(username, password)
            auth_error_text.value = "Акаунт створено та увійдено"
            page.update()
            handle_successful_login(profile)
        else:
            auth_error_text.value = "Логін вже зайнятий"
            page.update()
    
    def toggle_register_mode(e=None):
        """Перемикання між режимом входу та реєстрації"""
        nonlocal is_register_mode
        is_register_mode = not is_register_mode
        login_confirm_field.visible = is_register_mode
        auth_error_text.value = ""
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
                        ft.Text("Вхід / Реєстрація", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                        login_username_field,
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
            best_time_label.value = "Найкращий час: --:--"
            return
        stats = fetch_profile_stats(current_profile["id"])
        games_label.value = f"Ігор: {stats['games']}"
        best_time_label.value = (
            f"Найкращий час: {format_duration(stats['best'])}"
            if stats["best"] is not None
            else "Найкращий час: --:--"
        )


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
            insert_profile_record(current_profile["id"], duration, timestamp)
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

    def start_new_game(e=None, show_notification=True):
        nonlocal board, hints_remaining, shuffle_remaining, timer_started, elapsed_seconds, start_time
        nonlocal current_session_id
        timer_control.stop()
        board = Board()
        hints_remaining = 2
        shuffle_remaining = 1
        timer_started = False
        elapsed_seconds = 0
        start_time = 0.0
        timer_text.value = format_duration(0)
        pause_overlay.visible = False
        pause_overlay.opacity = 0
        results_overlay.visible = False
        results_overlay.opacity = 0
        board_container.opacity = 1
        # Приховуємо кнопку "Старт", бо гра починається
        if start_button:
            start_button.visible = False
        update_action_ui()
        update_board()
        if show_notification:
            page.snack_bar = ft.SnackBar(ft.Text("Нова гра розпочата"), open=True)
        refresh_leaderboard()

    def finalize_game(result_label: str):
        nonlocal current_session_id
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
        detail_text = [
            ft.Text("Фініш", size=30, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
            ft.Text(f"Час: {format_duration(record_duration)}", size=20, color=TEXT_COLOR),
            ft.Text(
                "Новий рекорд!" if new_record else "Рекорд не побито",
                color=HINT_COLOR if new_record else "#999",
            ),
        ]
        new_game_button = ft.ElevatedButton("Нова гра", on_click=start_new_game)
        results_overlay.content.controls = detail_text + [new_game_button]
        results_overlay.visible = True
        results_overlay.opacity = 0.95
        board_container.opacity = 1
        pause_overlay.visible = False
        pause_overlay.opacity = 0
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
        tile1, tile2 = pair
        tile1.highlighted = True
        tile2.highlighted = True
        update_action_ui()
        update_board()

    def request_shuffle(e):
        nonlocal shuffle_remaining
        # Перевіряємо, чи гра почалася
        if start_button and start_button.visible:
            return
        if is_paused:
            return
        if shuffle_remaining <= 0 or board.game_over:
            return
        shuffle_remaining -= 1
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
        if not board.has_possible_moves():
            show_reshuffle_prompt()
        results_overlay.visible = False

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
    
    sidebar = ft.Container(
        width=220,
        height=780,
        bgcolor=UI_PANEL_COLOR,
        padding=ft.padding.all(12),
        border=ft.border.all(1, "#2b2b2b"),
        border_radius=10,
        content=ft.Column(
                [
                    profile_label,
                    ft.Row([games_label, best_time_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    hint_button,
                    shuffle_button,
                    pause_button,
                    leaderboard_button,
                    admin_button,  # Адмінська кнопка для тестування
                    ft.Divider(height=1, color="#2b2b2b"),
                    ft.Text("Таймер", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    timer_text,
                    ft.Divider(height=1, color="#2b2b2b"),
                    ft.Text("Рекорди", size=16, weight=ft.FontWeight.BOLD, color=TEXT_COLOR),
                    records_table,
                ],
            spacing=12,
        ),
    )
    content_row = ft.Row(
        [
            ft.Container(content=board_container, expand=True, alignment=ft.alignment.top_left),
            sidebar,
        ],
        spacing=12,
        expand=True,
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    # Створюємо головний контейнер з Stack для overlay
    main_stack = ft.Stack(
        [
            content_row,
        ],
        expand=True,
    )
    print(f"DEBUG: main_stack створено, controls count={len(main_stack.controls)}")
    update_action_ui()
    def create_tile_container(tile: Tile) -> ft.Container:
        """Створює контейнер для плитки"""
        board_start_x = 10
        board_start_y = 10

        screen_x = board_start_x + tile.x * TILE_SPACING_X
        screen_y = board_start_y + tile.y * TILE_SPACING_Y

        if tile.highlighted:
            border_color = HINT_COLOR
            border_width = 4
            tile_bgcolor = "#FFF9D5"
        else:
            border_color = SELECTED_COLOR if tile.selected else AVAILABLE_COLOR
            border_width = 4 if tile.selected else 2
            tile_bgcolor = TILE_COLOR

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

        container = ft.Container(
            content=tile_content,
            left=screen_x,
            top=screen_y,
            width=TILE_WIDTH,
            height=TILE_HEIGHT,
            border=ft.border.all(border_width, border_color),
            border_radius=5,
            bgcolor=tile_bgcolor,
            opacity=1.0,
            on_click=lambda e, t=tile: tile_clicked(t),
        )

        tile.ui_element = container
        return container
    
    def tile_clicked(tile: Tile):
        """Обробник кліку по плитці"""
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
        board.clear_highlights()
        board.click_tile(tile)
        update_board()
    
    start_button: Optional[ft.ElevatedButton]

    def initialize_start_button():
        nonlocal start_button
        start_button = ft.ElevatedButton(
            "Однокористувацький режим",
            width=220,
            height=40,
            on_click=lambda e: load_tiles(),
        )
        # Кнопка не видима до входу користувача
        start_button.visible = False

    def load_tiles():
        nonlocal start_button, current_session_id
        start_button.visible = False
        if current_profile["id"] and current_session_id is None:
            current_session_id = start_session(current_profile["id"])
        start_timer(reset=True)
        update_board()
    
    def update_board():
        """Оновлює відображення дошки"""
        nonlocal main_stack
        print(f"DEBUG update_board: current_profile['id']={current_profile['id']}")
        board_container.controls.clear()
        
        # Якщо користувач увійшов, але гра ще не почалася - показуємо кнопку режиму в верхньому лівому куті
        if current_profile["id"] is not None and start_button and start_button.visible:
            board_container.controls.append(
                ft.Container(
                    content=start_button,
                    left=10,
                    top=10,
                )
            )
        # Якщо гра активна - показуємо плитки
        elif current_profile["id"] is not None:
            for tile in sorted(board.tiles, key=lambda t: (t.z, t.y, t.x)):
                if not tile.removed:
                    tile_container = create_tile_container(tile)
                    board_container.controls.append(tile_container)
        
        # Додаємо overlay елементи
        board_container.controls.append(pause_overlay)
        board_container.controls.append(results_overlay)
        
        # Оновлюємо сторінку
        update_action_ui()
        page.update()
        # Панель інформації прибрано повністю
        check_game_state()

    initialize_start_button()
    
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
    ft.app(target=main)

