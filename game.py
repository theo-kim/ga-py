import random
import os
import sys

# Platform-specific key reader
if os.name == 'nt':
    import msvcrt
    def get_key():
        ch = msvcrt.getch()
        return ch.decode('utf-8').lower()
else:
    import tty, termios
    def get_key():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch.lower()

# Maze symbols
WALL = '#'
FLOOR = ' '
PLAYER = 'P'
FINISH = 'F'
UNKNOWN = '.'
FLOOR_VISIBLE = ' '

# ===== Health config =====
STARTING_HEALTH = 100     # default if user skips prompt
STEP_COST = 1             # health lost per successful step

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def clamp_odd(n, minimum=5, maximum=501):
    n = max(minimum, min(maximum, n))
    return n if n % 2 == 1 else n - 1

def carve_passages(width, height):
    grid = [[WALL for _ in range(width)] for _ in range(height)]

    def inb(y, x): return 0 <= y < height and 0 <= x < width

    start_y = random.randrange(1, height, 2)
    start_x = random.randrange(1, width, 2)
    grid[start_y][start_x] = FLOOR

    stack = [(start_y, start_x)]
    DIRS = [(-2, 0), (2, 0), (0, -2), (0, 2)]

    while stack:
        y, x = stack[-1]
        random.shuffle(DIRS)
        carved = False
        for dy, dx in DIRS:
            ny, nx = y + dy, x + dx
            if inb(ny, nx) and grid[ny][nx] == WALL:
                wy, wx = y + dy // 2, x + dx // 2
                grid[wy][wx] = FLOOR
                grid[ny][nx] = FLOOR
                stack.append((ny, nx))
                carved = True
                break
        if not carved:
            stack.pop()

    # Outer border solid
    for i in range(width):
        grid[0][i] = WALL
        grid[height - 1][i] = WALL
    for j in range(height):
        grid[j][0] = WALL
        grid[j][width - 1] = WALL

    return grid

def random_open_cell(grid):
    h, w = len(grid), len(grid[0])
    while True:
        y = random.randrange(1, h - 1)
        x = random.randrange(1, w - 1)
        if grid[y][x] == FLOOR:
            return y, x

def bresenham_line(y0, x0, y1, x1):
    """Yield grid cells on a line from (y0,x0) to (y1,x1), inclusive."""
    dy = abs(y1 - y0)
    dx = abs(x1 - x0)
    sy = 1 if y0 < y1 else -1
    sx = 1 if x0 < x1 else -1
    err = dx - dy
    y, x = y0, x0
    while True:
        yield y, x
        if y == y1 and x == x1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy

def visible_cells_radius(grid, py, px, radius):
    """
    Field-of-view: Euclidean radius with occlusion via Bresenham LOS.
    Returns a set of visible (y,x).
    """
    h, w = len(grid), len(grid[0])
    r2 = radius * radius
    vis = set()
    vis.add((py, px))

    y_min = max(0, py - radius)
    y_max = min(h - 1, py + radius)
    x_min = max(0, px - radius)
    x_max = min(w - 1, px + radius)

    def opaque(y, x):
        return grid[y][x] == WALL

    for y in range(y_min, y_max + 1):
        for x in range(x_min, x_max + 1):
            dy = y - py
            dx = x - px
            if dy*dy + dx*dx > r2:
                continue  # outside radius

            blocked = False
            first = True
            for cy, cx in bresenham_line(py, px, y, x):
                if first:
                    first = False
                    continue  # skip the player cell
                if opaque(cy, cx) and (cy, cx) != (y, x):
                    blocked = True
                    break
            if not blocked:
                vis.add((y, x))
    return vis

def render(grid, py, px, fy, fx, health):
    h, w = len(grid), len(grid[0])
    vis = visible_cells_radius(grid, py, px, 5)

    lines = []
    for y in range(h):
        row_chars = []
        for x in range(w):
            if (y, x) == (py, px):
                row_chars.append(PLAYER)
            elif (y, x) == (fy, fx) and (y, x) in vis:
                row_chars.append(FINISH)
            elif (y, x) in vis:
                row_chars.append(WALL if grid[y][x] == WALL else FLOOR_VISIBLE)
            else:
                row_chars.append(UNKNOWN)
        lines.append(''.join(row_chars))
    hud = f"Health: {health}   Controls: w/a/s/d to move, q to quit"
    return hud + "\n" + "\n".join(lines)

def main():
    clear()
    print("Maze Game")
    print("----------")
    print("Controls: w=up, a=left, s=down, d=right, q=quit")
    print()

    try:
        width = int(input("Enter maze width  (odd recommended, min 5): ").strip())
        height = int(input("Enter maze height (odd recommended, min 5): ").strip())
    except Exception:
        print("Invalid input. Using defaults 41x21.")
        width, height = 41, 21

    width = clamp_odd(width)
    height = clamp_odd(height)

    # Health prompt (optional)
    try:
        val = input(f"Starting health (default {STARTING_HEALTH}): ").strip()
        health = int(val) if val else STARTING_HEALTH
    except Exception:
        health = STARTING_HEALTH

    grid = carve_passages(width, height)
    py, px = random_open_cell(grid)
    fy, fx = random_open_cell(grid)
    while (fy, fx) == (py, px):
        fy, fx = random_open_cell(grid)

    move_map = {
        'w': (-1, 0),
        'a': (0, -1),
        's': (1, 0),
        'd': (0, 1),
    }

    while True:
        clear()
        print(render(grid, py, px, fy, fx, health))
        key = get_key()

        if key == 'q':
            print("Goodbye!")
            break

        if key in move_map:
            dy, dx = move_map[key]
            ny, nx = py + dy, px + dx
            if 0 <= ny < height and 0 <= nx < width and grid[ny][nx] != WALL:
                py, px = ny, nx
            health -= STEP_COST
            if health <= 0 :
                clear()
                print("\n💀 You ran out of health. Game over!")
                exit(1)

        if (py, px) == (fy, fx):
            clear()
            print(render(grid, py, px, fy, fx, health))
            print("\n🎉 You reached the finish! 🎉")
            exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)
