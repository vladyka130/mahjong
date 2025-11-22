"""
Mahjong Solitaire Game
Класична гра-головоломка з плитками маджонгу
"""

import pygame
import random
import math
import os
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict
from enum import Enum

# Ініціалізація Pygame
pygame.init()

# Константи
SCREEN_WIDTH = 1400
SCREEN_HEIGHT = 900
TILE_WIDTH = 50
TILE_HEIGHT = 70
TILE_DEPTH = 15  # Висота для 3D ефекту
TILE_SPACING_X = 52  # Відстань між плитками по X
TILE_SPACING_Y = 55  # Відстань між плитками по Y

# Кольори
BACKGROUND_COLOR = (20, 80, 20)  # Темно-зелений
TILE_COLOR = (255, 255, 240)  # Кремовий
TILE_BORDER = (200, 200, 180)
SELECTED_COLOR = (255, 215, 0)  # Золотий
AVAILABLE_COLOR = (144, 238, 144)  # Світло-зелений
BLOCKED_COLOR = (100, 100, 100)  # Сірий для заблокованих
UI_PANEL_COLOR = (30, 30, 30)  # Темна панель
TEXT_COLOR = (255, 255, 255)
HINT_COLOR = (255, 200, 100)  # Помаранчевий для підказок


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
    
    # Квіти/Сезони (спеціальні)
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
        self.x = x  # Позиція на дошці
        self.y = y
        self.z = z  # Шар (для 3D ефекту)
        self.selected = False
        self.removed = False
        
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
        self.generate_board()
        
    def generate_board(self):
        """Генерує дошку з плитками у вигляді патерну"""
        # Створюємо набір плиток (кожна плитка має бути в парі)
        # Використовуємо тільки основні типи (без квітів і сезонів для простоти)
        basic_tile_types = [
            TileType.BAMBOO_1, TileType.BAMBOO_2, TileType.BAMBOO_3, TileType.BAMBOO_4,
            TileType.BAMBOO_5, TileType.BAMBOO_6, TileType.BAMBOO_7, TileType.BAMBOO_8, TileType.BAMBOO_9,
            TileType.DOT_1, TileType.DOT_2, TileType.DOT_3, TileType.DOT_4,
            TileType.DOT_5, TileType.DOT_6, TileType.DOT_7, TileType.DOT_8, TileType.DOT_9,
            TileType.WAN_1, TileType.WAN_2, TileType.WAN_3, TileType.WAN_4,
            TileType.WAN_5, TileType.WAN_6, TileType.WAN_7, TileType.WAN_8, TileType.WAN_9,
            TileType.EAST, TileType.SOUTH, TileType.WEST, TileType.NORTH,
            TileType.RED_DRAGON, TileType.GREEN_DRAGON, TileType.WHITE_DRAGON,
        ]
        
        pairs = []
        
        # Створюємо 72 пари (144 плитки загалом для патерну Turtle)
        # Кожен тип з'являється 4 рази (2 пари)
        for tile_type in basic_tile_types:
            pairs.extend([tile_type, tile_type, tile_type, tile_type])
        
        random.shuffle(pairs)
        
        # Створюємо патерн дошки
        pattern = self._create_pyramid_pattern()
        
        tile_index = 0
        for z, layer in enumerate(pattern):
            for y, row in enumerate(layer):
                for x, has_tile in enumerate(row):
                    if has_tile and tile_index < len(pairs):
                        self.tiles.append(Tile(pairs[tile_index], x, y, z))
                        tile_index += 1
    
    def _create_pyramid_pattern(self) -> List[List[List[bool]]]:
        """Створює класичний патерн Turtle для Mahjong Solitaire"""
        # Класичний патерн Turtle - найпопулярніший патерн
        pattern = []
        
        # Шар 0 (нижній) - 144 плитки
        layer0 = [
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False],
            [False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False],
            [False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False],
            [False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False],
            [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True],
            [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True],
            [False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False],
            [False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False],
            [False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False],
            [False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
        ]
        
        # Шар 1 - 100 плиток
        layer1 = [
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, True, True, True, True, True, True, True, True, False, False, False, False, False],
            [False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False],
            [False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False],
            [False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False],
            [False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False],
            [False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False],
            [False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False],
            [False, False, False, False, False, True, True, True, True, True, True, True, True, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
        ]
        
        # Шар 2 - 64 плитки
        layer2 = [
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, True, True, True, True, True, True, False, False, False, False, False, False],
            [False, False, False, False, False, True, True, True, True, True, True, True, True, False, False, False, False, False],
            [False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False],
            [False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, False, False],
            [False, False, False, False, False, True, True, True, True, True, True, True, True, False, False, False, False, False],
            [False, False, False, False, False, False, True, True, True, True, True, True, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
        ]
        
        # Шар 3 (верхній) - 36 плиток
        layer3 = [
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, True, True, True, True, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, True, True, True, True, True, True, False, False, False, False, False, False],
            [False, False, False, False, False, False, True, True, True, True, True, True, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, True, True, True, True, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
        ]
        
        return [layer0, layer1, layer2, layer3]
    
    def is_tile_available(self, tile: Tile) -> bool:
        """Перевіряє, чи плитка доступна для видалення (не заблокована зверху або з боків)"""
        if tile.removed:
            return False
        
        # Перевіряємо, чи немає плиток зверху на тому ж x, y
        for other_tile in self.tiles:
            if other_tile.removed:
                continue
            if other_tile.x == tile.x and other_tile.y == tile.y and other_tile.z > tile.z:
                return False
        
        # Перевіряємо, чи немає плиток з боків на тому ж z рівні
        # Плитка доступна, якщо зліва або справа немає плиток на тому ж рівні
        left_blocked = False
        right_blocked = False
        
        for other_tile in self.tiles:
            if other_tile.removed:
                continue
            if other_tile.z == tile.z:
                if other_tile.y == tile.y:
                    if other_tile.x == tile.x - 1:
                        left_blocked = True
                    if other_tile.x == tile.x + 1:
                        right_blocked = True
        
        # Плитка доступна, якщо вона не заблокована з обох боків одночасно
        return not (left_blocked and right_blocked)
    
    def get_available_tiles(self) -> List[Tile]:
        """Повертає список доступних плиток"""
        return [tile for tile in self.tiles if self.is_tile_available(tile)]
    
    def click_tile(self, tile: Tile):
        """Обробляє клік по плитці"""
        if tile.removed:
            return
        
        if not self.is_tile_available(tile):
            # Якщо плитка заблокована, скасовуємо вибір (якщо є)
            if self.selected_tile:
                self.selected_tile.selected = False
                self.selected_tile = None
            return
        
        if self.selected_tile is None:
            # Вибираємо першу плитку
            self.selected_tile = tile
            tile.selected = True
        elif self.selected_tile is tile:
            # Скасовуємо вибір, якщо клікнули на ту саму плитку (той самий об'єкт)
            self.selected_tile.selected = False
            self.selected_tile = None
        elif self.selected_tile.tile_type == tile.tile_type:
            # Знайдено пару! Перевіряємо, що обидві доступні
            if self.is_tile_available(self.selected_tile) and self.is_tile_available(tile):
                # Видаляємо обидві плитки
                self.selected_tile.removed = True
                tile.removed = True
                self.selected_tile.selected = False
                self.selected_tile = None
            else:
                # Якщо одна з плиток стала недоступною, скасовуємо вибір
                self.selected_tile.selected = False
                self.selected_tile = tile
                tile.selected = True
        else:
            # Вибираємо іншу плитку
            self.selected_tile.selected = False
            self.selected_tile = tile
            tile.selected = True
    
    def is_game_won(self) -> bool:
        """Перевіряє, чи виграна гра"""
        return all(tile.removed for tile in self.tiles)
    
    def is_game_lost(self) -> bool:
        """Перевіряє, чи програна гра (немає доступних пар)"""
        available = self.get_available_tiles()
        if len(available) < 2:
            return True
        
        # Перевіряємо, чи є хоча б одна пара серед доступних
        for i, tile1 in enumerate(available):
            for tile2 in available[i+1:]:
                if tile1 == tile2:
                    return False
        return True


class Game:
    """Головний клас гри"""
    
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Mahjong Solitaire")
        self.clock = pygame.time.Clock()
        self.board = Board()
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.running = True
        self.tile_images: Dict[TileType, pygame.Surface] = {}
        self.load_tile_images()
    
    def load_tile_images(self):
        """Завантажує зображення плиток з папки assets/tiles"""
        tiles_dir = Path("assets/tiles")
        
        # Маппінг між TileType і можливими назвами файлів
        tile_file_mapping = {
            # Бамбук (Sou)
            TileType.BAMBOO_1: ["Sou1.png", "sou1.png", "SOU1.png", "b1.png", "bamboo1.png", "1b.png", "bamboo_1.png"],
            TileType.BAMBOO_2: ["Sou2.png", "sou2.png", "SOU2.png", "b2.png", "bamboo2.png", "2b.png", "bamboo_2.png"],
            TileType.BAMBOO_3: ["Sou3.png", "sou3.png", "SOU3.png", "b3.png", "bamboo3.png", "3b.png", "bamboo_3.png"],
            TileType.BAMBOO_4: ["Sou4.png", "sou4.png", "SOU4.png", "b4.png", "bamboo4.png", "4b.png", "bamboo_4.png"],
            TileType.BAMBOO_5: ["Sou5.png", "sou5.png", "SOU5.png", "b5.png", "bamboo5.png", "5b.png", "bamboo_5.png"],
            TileType.BAMBOO_6: ["Sou6.png", "sou6.png", "SOU6.png", "b6.png", "bamboo6.png", "6b.png", "bamboo_6.png"],
            TileType.BAMBOO_7: ["Sou7.png", "sou7.png", "SOU7.png", "b7.png", "bamboo7.png", "7b.png", "bamboo_7.png"],
            TileType.BAMBOO_8: ["Sou8.png", "sou8.png", "SOU8.png", "b8.png", "bamboo8.png", "8b.png", "bamboo_8.png"],
            TileType.BAMBOO_9: ["Sou9.png", "sou9.png", "SOU9.png", "b9.png", "bamboo9.png", "9b.png", "bamboo_9.png"],
            # Крапки (Pin)
            TileType.DOT_1: ["Pin1.png", "pin1.png", "PIN1.png", "d1.png", "dot1.png", "1d.png", "dot_1.png", "circle1.png"],
            TileType.DOT_2: ["Pin2.png", "pin2.png", "PIN2.png", "d2.png", "dot2.png", "2d.png", "dot_2.png", "circle2.png"],
            TileType.DOT_3: ["Pin3.png", "pin3.png", "PIN3.png", "d3.png", "dot3.png", "3d.png", "dot_3.png", "circle3.png"],
            TileType.DOT_4: ["Pin4.png", "pin4.png", "PIN4.png", "d4.png", "dot4.png", "4d.png", "dot_4.png", "circle4.png"],
            TileType.DOT_5: ["Pin5.png", "pin5.png", "PIN5.png", "d5.png", "dot5.png", "5d.png", "dot_5.png", "circle5.png"],
            TileType.DOT_6: ["Pin6.png", "pin6.png", "PIN6.png", "d6.png", "dot6.png", "6d.png", "dot_6.png", "circle6.png"],
            TileType.DOT_7: ["Pin7.png", "pin7.png", "PIN7.png", "d7.png", "dot7.png", "7d.png", "dot_7.png", "circle7.png"],
            TileType.DOT_8: ["Pin8.png", "pin8.png", "PIN8.png", "d8.png", "dot8.png", "8d.png", "dot_8.png", "circle8.png"],
            TileType.DOT_9: ["Pin9.png", "pin9.png", "PIN9.png", "d9.png", "dot9.png", "9d.png", "dot_9.png", "circle9.png"],
            # Ван (Man)
            TileType.WAN_1: ["Man1.png", "man1.png", "MAN1.png", "w1.png", "wan1.png", "1w.png", "wan_1.png", "character1.png"],
            TileType.WAN_2: ["Man2.png", "man2.png", "MAN2.png", "w2.png", "wan2.png", "2w.png", "wan_2.png", "character2.png"],
            TileType.WAN_3: ["Man3.png", "man3.png", "MAN3.png", "w3.png", "wan3.png", "3w.png", "wan_3.png", "character3.png"],
            TileType.WAN_4: ["Man4.png", "man4.png", "MAN4.png", "w4.png", "wan4.png", "4w.png", "wan_4.png", "character4.png"],
            TileType.WAN_5: ["Man5.png", "man5.png", "MAN5.png", "w5.png", "wan5.png", "5w.png", "wan_5.png", "character5.png"],
            TileType.WAN_6: ["Man6.png", "man6.png", "MAN6.png", "w6.png", "wan6.png", "6w.png", "wan_6.png", "character6.png"],
            TileType.WAN_7: ["Man7.png", "man7.png", "MAN7.png", "w7.png", "wan7.png", "7w.png", "wan_7.png", "character7.png"],
            TileType.WAN_8: ["Man8.png", "man8.png", "MAN8.png", "w8.png", "wan8.png", "8w.png", "wan_8.png", "character8.png"],
            TileType.WAN_9: ["Man9.png", "man9.png", "MAN9.png", "w9.png", "wan9.png", "9w.png", "wan_9.png", "character9.png"],
            # Вітри
            TileType.EAST: ["Ton.png", "ton.png", "TON.png", "east.png", "wind_east.png", "e.png"],
            TileType.SOUTH: ["Nan.png", "nan.png", "NAN.png", "south.png", "wind_south.png", "s.png"],
            TileType.WEST: ["Shaa.png", "shaa.png", "SHAA.png", "west.png", "wind_west.png", "w.png"],
            TileType.NORTH: ["Pei.png", "pei.png", "PEI.png", "north.png", "wind_north.png", "n.png"],
            # Дракони
            TileType.RED_DRAGON: ["Chun.png", "chun.png", "CHUN.png", "red_dragon.png", "dragon_red.png", "rd.png", "zhong.png"],
            TileType.GREEN_DRAGON: ["Hatsu.png", "hatsu.png", "HATSU.png", "green_dragon.png", "dragon_green.png", "gd.png", "fa.png"],
            TileType.WHITE_DRAGON: ["Haku.png", "haku.png", "HAKU.png", "white_dragon.png", "dragon_white.png", "wd.png", "bai.png"],
            # Квіти
            TileType.FLOWER_PLUM: ["flower_plum.png", "plum.png", "fp.png"],
            TileType.FLOWER_ORCHID: ["flower_orchid.png", "orchid.png", "fo.png"],
            TileType.FLOWER_CHRYSANTHEMUM: ["flower_chrys.png", "chrysanthemum.png", "fc.png"],
            TileType.FLOWER_BAMBOO: ["flower_bamboo.png", "bamboo_flower.png", "fb.png"],
            # Сезони
            TileType.SEASON_SPRING: ["season_spring.png", "spring.png", "ss.png"],
            TileType.SEASON_SUMMER: ["season_summer.png", "summer.png", "ssu.png"],
            TileType.SEASON_AUTUMN: ["season_autumn.png", "autumn.png", "sa.png"],
            TileType.SEASON_WINTER: ["season_winter.png", "winter.png", "sw.png"],
        }
        
        if not tiles_dir.exists():
            print(f"⚠️  Папка {tiles_dir} не знайдена. Створюю...")
            tiles_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 Створено папку {tiles_dir}")
            print("💡 Завантаж зображення плиток у цю папку")
            return
        
        # Завантажуємо зображення для кожного типу плитки
        loaded_count = 0
        
        # Спочатку отримуємо список всіх файлів у папці (case-insensitive)
        existing_files = {}
        if tiles_dir.exists():
            for file_path in tiles_dir.glob("*.png"):
                existing_files[file_path.name.lower()] = file_path
        
        for tile_type, possible_names in tile_file_mapping.items():
            image_loaded = False
            for filename in possible_names:
                # Перевіряємо точну назву
                file_path = tiles_dir / filename
                if file_path.exists():
                    try:
                        img = pygame.image.load(str(file_path))
                        # Масштабуємо до розміру плитки
                        img = pygame.transform.scale(img, (TILE_WIDTH, TILE_HEIGHT))
                        self.tile_images[tile_type] = img
                        image_loaded = True
                        loaded_count += 1
                        break
                    except pygame.error as e:
                        print(f"⚠️  Помилка завантаження {filename}: {e}")
                # Перевіряємо case-insensitive
                elif filename.lower() in existing_files:
                    try:
                        actual_path = existing_files[filename.lower()]
                        img = pygame.image.load(str(actual_path))
                        img = pygame.transform.scale(img, (TILE_WIDTH, TILE_HEIGHT))
                        self.tile_images[tile_type] = img
                        image_loaded = True
                        loaded_count += 1
                        break
                    except pygame.error as e:
                        print(f"⚠️  Помилка завантаження {actual_path.name}: {e}")
            
            if not image_loaded:
                # Якщо зображення не знайдено, створюємо placeholder
                placeholder = pygame.Surface((TILE_WIDTH, TILE_HEIGHT))
                placeholder.fill(TILE_COLOR)
                pygame.draw.rect(placeholder, TILE_BORDER, (0, 0, TILE_WIDTH, TILE_HEIGHT), 2)
                # Додаємо текст як fallback
                text = self.small_font.render(tile_type.value, True, (0, 0, 0))
                text_rect = text.get_rect(center=(TILE_WIDTH // 2, TILE_HEIGHT // 2))
                placeholder.blit(text, text_rect)
                self.tile_images[tile_type] = placeholder
        
        if loaded_count > 0:
            print(f"✅ Завантажено {loaded_count} зображень плиток")
        else:
            print("⚠️  Зображення плиток не знайдено. Використовуються placeholder'и.")
            print(f"💡 Завантаж зображення у папку {tiles_dir}")
        
    def get_tile_at_position(self, pos: Tuple[int, int]) -> Optional[Tile]:
        """Знаходить плитку за координатами миші"""
        mouse_x, mouse_y = pos
        
        # Центруємо дошку (та сама логіка, що й у draw_tile)
        board_center_x = SCREEN_WIDTH // 2
        board_start_x = board_center_x - (9 * TILE_SPACING_X)
        
        # Перевіряємо плитки зверху вниз (спочатку верхні шари)
        for tile in sorted(self.board.tiles, key=lambda t: (-t.z, t.y, t.x)):
            if tile.removed:
                continue
            
            # Обчислюємо позицію плитки на екрані з урахуванням 3D (та сама формула, що й у draw_tile)
            screen_x = board_start_x + tile.x * TILE_SPACING_X + tile.z * 3
            screen_y = 120 + tile.y * TILE_SPACING_Y + tile.z * 8
            
            if (screen_x <= mouse_x <= screen_x + TILE_WIDTH and
                screen_y <= mouse_y <= screen_y + TILE_HEIGHT):
                return tile
        return None
    
    def draw_tile(self, tile: Tile):
        """Малює одну плитку"""
        if tile.removed:
            return
        
        # Центруємо дошку
        board_center_x = SCREEN_WIDTH // 2
        board_start_x = board_center_x - (9 * TILE_SPACING_X)
        
        # Обчислюємо позицію з урахуванням 3D
        screen_x = board_start_x + tile.x * TILE_SPACING_X + tile.z * 3
        screen_y = 120 + tile.y * TILE_SPACING_Y + tile.z * 8
        
        # Отримуємо зображення плитки
        tile_image = self.tile_images.get(tile.tile_type)
        
        if tile_image:
            # Перевіряємо доступність
            is_available = self.board.is_tile_available(tile)
            
            # Якщо плитка вибрана, додаємо золотий контур
            if tile.selected:
                # Товстіший золотий контур для вибраної
                pygame.draw.rect(self.screen, SELECTED_COLOR,
                               (screen_x - 4, screen_y - 4, TILE_WIDTH + 8, TILE_HEIGHT + 8), 4)
            elif is_available:
                # Тонкий зелений контур для доступних плиток
                pygame.draw.rect(self.screen, AVAILABLE_COLOR,
                               (screen_x - 2, screen_y - 2, TILE_WIDTH + 4, TILE_HEIGHT + 4), 2)
            
            # Малюємо саму плитку
            self.screen.blit(tile_image, (screen_x, screen_y))
            
            # Якщо плитка заблокована, додаємо затемнення
            if not is_available:
                overlay = pygame.Surface((TILE_WIDTH, TILE_HEIGHT))
                overlay.set_alpha(150)
                overlay.fill(BLOCKED_COLOR)
                self.screen.blit(overlay, (screen_x, screen_y))
        else:
            # Fallback: малюємо плитку без зображення (старий спосіб)
            color = SELECTED_COLOR if tile.selected else (TILE_COLOR if self.board.is_tile_available(tile) else (200, 200, 200))
            pygame.draw.rect(self.screen, color, (screen_x, screen_y, TILE_WIDTH, TILE_HEIGHT))
            pygame.draw.rect(self.screen, TILE_BORDER, (screen_x, screen_y, TILE_WIDTH, TILE_HEIGHT), 2)
            text = self.small_font.render(tile.get_display_name(), True, (0, 0, 0))
            text_rect = text.get_rect(center=(screen_x + TILE_WIDTH // 2, screen_y + TILE_HEIGHT // 2))
            self.screen.blit(text, text_rect)
        
        # Бічна грань (для 3D ефекту)
        if tile.z > 0:
            color = TILE_COLOR if self.board.is_tile_available(tile) else (200, 200, 200)
            points = [
                (screen_x, screen_y + TILE_HEIGHT),
                (screen_x + TILE_DEPTH, screen_y + TILE_HEIGHT + TILE_DEPTH),
                (screen_x + TILE_WIDTH + TILE_DEPTH, screen_y + TILE_HEIGHT + TILE_DEPTH),
                (screen_x + TILE_WIDTH, screen_y + TILE_HEIGHT)
            ]
            pygame.draw.polygon(self.screen, (color[0] - 30, color[1] - 30, color[2] - 30), points)
    
    def draw_ui_panel(self):
        """Малює панель з інформацією та інструкціями"""
        panel_width = 280
        panel_x = SCREEN_WIDTH - panel_width - 10
        panel_y = 10
        
        # Напівпрозорий фон панелі
        panel_surface = pygame.Surface((panel_width, SCREEN_HEIGHT - 20))
        panel_surface.set_alpha(220)
        panel_surface.fill(UI_PANEL_COLOR)
        self.screen.blit(panel_surface, (panel_x, panel_y))
        
        y_offset = panel_y + 15
        
        # Заголовок
        title = self.font.render("Mahjong Solitaire", True, TEXT_COLOR)
        self.screen.blit(title, (panel_x + 10, y_offset))
        y_offset += 40
        
        # Статистика
        total_tiles = len(self.board.tiles)
        removed_tiles = sum(1 for t in self.board.tiles if t.removed)
        remaining = total_tiles - removed_tiles
        
        stats_text = self.small_font.render(f"Плиток: {remaining} / {total_tiles}", True, TEXT_COLOR)
        self.screen.blit(stats_text, (panel_x + 10, y_offset))
        y_offset += 30
        
        # Прогрес-бар
        if total_tiles > 0:
            progress = removed_tiles / total_tiles
            bar_width = panel_width - 20
            bar_height = 20
            pygame.draw.rect(self.screen, (50, 50, 50), 
                           (panel_x + 10, y_offset, bar_width, bar_height))
            pygame.draw.rect(self.screen, (0, 255, 0), 
                           (panel_x + 10, y_offset, int(bar_width * progress), bar_height))
        y_offset += 35
        
        # Інструкції
        instructions = [
            "ПРАВИЛА ГРИ:",
            "",
            "1. Знайди пари однакових",
            "   плиток",
            "",
            "2. Плитка доступна, якщо:",
            "   - Не заблокована зверху",
            "   - Вільна зліва АБО справа",
            "",
            "3. Клікни на плитку, щоб",
            "   вибрати (золота підсвітка)",
            "",
            "4. Клікни на іншу таку ж",
            "   плитку - пара видалиться",
            "",
            "5. Виграй, видаливши всі",
            "   плитки!",
        ]
        
        for line in instructions:
            if line:
                text = self.small_font.render(line, True, TEXT_COLOR)
                self.screen.blit(text, (panel_x + 10, y_offset))
            y_offset += 20
        
        y_offset += 10
        
        # Підказки про доступні пари
        available = self.board.get_available_tiles()
        if available:
            # Шукаємо доступні пари
            pairs_found = []
            for i, tile1 in enumerate(available):
                for tile2 in available[i+1:]:
                    if tile1 == tile2:
                        pairs_found.append((tile1.tile_type, tile1.get_display_name()))
                        break
            
            if pairs_found:
                hint_text = self.small_font.render("Доступні пари:", True, HINT_COLOR)
                self.screen.blit(hint_text, (panel_x + 10, y_offset))
                y_offset += 25
                
                for tile_type, name in pairs_found[:5]:  # Показуємо до 5 пар
                    pair_text = self.small_font.render(f"  • {name}", True, HINT_COLOR)
                    self.screen.blit(pair_text, (panel_x + 10, y_offset))
                    y_offset += 20
        
        # Статус гри
        y_offset = SCREEN_HEIGHT - 80
        if self.board.is_game_won():
            status_text = self.font.render("ВИГРАВ! 🎉", True, SELECTED_COLOR)
            text_rect = status_text.get_rect(center=(panel_x + panel_width // 2, y_offset))
            self.screen.blit(status_text, text_rect)
        elif self.board.is_game_lost():
            status_text = self.font.render("ПРОГРАВ 😢", True, (255, 100, 100))
            text_rect = status_text.get_rect(center=(panel_x + panel_width // 2, y_offset))
            self.screen.blit(status_text, text_rect)
    
    def draw(self):
        """Малює весь екран"""
        self.screen.fill(BACKGROUND_COLOR)
        
        # Малюємо всі плитки
        for tile in sorted(self.board.tiles, key=lambda t: (t.z, t.y, t.x)):
            self.draw_tile(tile)
        
        # Малюємо UI панель
        self.draw_ui_panel()
        
        pygame.display.flip()
    
    def handle_events(self):
        """Обробляє події"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Ліва кнопка миші
                    tile = self.get_tile_at_position(event.pos)
                    if tile:
                        self.board.click_tile(tile)
    
    def run(self):
        """Головний цикл гри"""
        while self.running:
            self.handle_events()
            self.draw()
            self.clock.tick(60)
        
        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()

