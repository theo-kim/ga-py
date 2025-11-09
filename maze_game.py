import random
from typing import Dict, Any, List

# Maze symbols
WALL = '#'
FLOOR = ' '

class Maze:
    """
    Represents a single maze instance, handling generation and player state.
    """
    def __init__(self, width: int | None = None, height: int | None = None, from_data: Dict[str, Any] | None = None):
        if from_data:
            self.width = from_data['width']
            self.height = from_data['height']
            self.grid = from_data['grid']
            self.start_position = tuple(from_data['start_position'])
            self.finish_y, self.finish_x = tuple(from_data['finish_position'])
        else:
            if width is None or height is None:
                raise ValueError("Width and height must be provided for new maze generation.")
            if width % 2 == 0: width += 1
            if height % 2 == 0: height += 1
            self.width = width
            self.height = height
            self.grid = self._carve_passages()
            self.start_position = self._random_open_cell()
            self.finish_y, self.finish_x = self._random_open_cell()
            while (self.finish_y, self.finish_x) == self.start_position:
                self.finish_y, self.finish_x = self._random_open_cell()


        self.reset()

    def move(self, direction: str) -> bool:
        """
        Moves the player one step in the given direction ('w', 'a', 's', 'd').
        Returns True if the move was valid (into an open space), False otherwise.
        """
        self.total_steps += 1
        move_map = {'w': (-1, 0), 'a': (0, -1), 's': (1, 0), 'd': (0, 1)}
        dy, dx = move_map[direction]
        ny, nx = self.player_y + dy, self.player_x + dx

        if 0 <= ny < self.height and 0 <= nx < self.width and self.grid[ny][nx] != WALL:
            self.player_y, self.player_x = ny, nx
            self.visited_cells.add((ny, nx))
            self.valid_moves += 1
            return True
        return False

    def reset(self) :
        """Reset the maze to its initial state and remove the statistics."""
        self.player_y, self.player_x = self.start_position
        self.total_steps = 0
        self.valid_moves = 0
        self.visited_cells = {(self.player_y, self.player_x)}

    def is_finished(self) -> bool:
        """Returns True if the player is at the finish coordinates."""
        return (self.player_y, self.player_x) == (self.finish_y, self.finish_x)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "grid": self.grid,
            "start_position": self.start_position,
            "finish_position": (self.finish_y, self.finish_x)
        }

    def _random_open_cell(self):
        while True:
            y = random.randrange(1, self.height - 1)
            x = random.randrange(1, self.width - 1)
            if self.grid[y][x] == FLOOR:
                return y, x

    def _carve_passages(self):
        """Generates the maze grid using a randomized depth-first search."""
        grid = [[WALL for _ in range(self.width)] for _ in range(self.height)]

        def inb(y, x):
            return 0 <= y < self.height and 0 <= x < self.width

        start_y = random.randrange(1, self.height, 2)
        start_x = random.randrange(1, self.width, 2)
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

        # Ensure the outer border is solid
        for i in range(self.width):
            grid[0][i] = WALL
            grid[self.height - 1][i] = WALL
        for j in range(self.height):
            grid[j][0] = WALL
            grid[j][self.width - 1] = WALL

        return grid