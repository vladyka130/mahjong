# pattern_coordinates.py
# Патерн плиток (x,y,z) — відповідно до системи:
# x: колонка (0 = найлівіша), y: рядок (0 = найвищий), z: шар (0=низ,1=серед,2=верх)

TILE_EMPTY = 0
TILE_GENERIC = "generic"
TILE_FLOWER  = "flower"
TILE_SPECIAL = "top-special"
TILE_SIDE    = "side"

# Розміри (я використовую 17 колонок x 9 рядків, як у попередньому прикладі)
COLS = 17
ROWS = 9
LAYERS_COUNT = 3  # 0=низ,1=серед,2=верх

# Шари у форматі [row0, row1, ...], кожен ряд — список довжини COLS.
# (Це ті самі масиви що в попередньому прикладі; пробіли = TILE_EMPTY)
# layer0 в попередньому прикладі був верхнім — тут він буде mapped -> z=2
layer_top = [
    [0,0,0,0,0,0,0,0, TILE_SPECIAL, 0,0,0,0,0,0,0,0],
    [0]*COLS,
    [0]*COLS,
    [0]*COLS,
    [0]*COLS,
    [0]*COLS,
    [0]*COLS,
    [0]*COLS,
    [0]*COLS
]

# layer1 — середній (mapped -> z=1)
layer_mid = [
    [0,0,0,0,0, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, 0,0,0,0,0,0],  # row 0
    [0,0,0,0, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC,0,0,0,0,0],  # row 1
    [0,0,0, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_FLOWER, TILE_GENERIC, TILE_GENERIC, TILE_FLOWER, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC,0,0,0,0],  # row 2
    [0,0, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC,0,0,0],  # row 3
    [0]*COLS,  # row 4
    [0]*COLS,  # row 5
    [0]*COLS,  # row 6
    [0]*COLS,  # row 7
    [0]*COLS   # row 8
]

# layer2 — базовий (mapped -> z=0)
layer_base = [
    [0, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC,0],  # row 0
    [TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_FLOWER, TILE_GENERIC, TILE_FLOWER, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC],  # row 1
    [TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC],  # row 2
    [0, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC, TILE_GENERIC,0],  # row 3
    [0]*COLS,  # row 4
    [0]*COLS,  # row 5
    [0]*COLS,  # row 6
    [0]*COLS,  # row 7
    [0]*COLS   # row 8
]

# Збираємо шари у порядок z=0 (низ), z=1 (серед), z=2 (верх)
LAYERS = [layer_base, layer_mid, layer_top]

def generate_tile_list():
    tiles = []
    for z, layer in enumerate(LAYERS):         # z: 0..2
        for y, row in enumerate(layer):        # y: 0..ROWS-1
            for x, cell in enumerate(row):    # x: 0..COLS-1
                if cell != 0:
                    tile_type = cell
                    tiles.append({"x": x, "y": y, "z": z, "type": tile_type})
    return tiles

if __name__ == "__main__":
    # Параметр: шлях до оригінального скріну (для дебагу)
    reference_image = "/mnt/data/dc9e14de-ea21-4ee9-9adf-e2c9058924b8.png"
    tiles = generate_tile_list()
    print(f"Reference image: {reference_image}")
    print(f"Total tiles: {len(tiles)}")
    # Друкуємо всі координати
    for t in tiles:
        print(t)