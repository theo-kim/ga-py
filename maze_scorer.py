from __future__ import annotations
from typing import TYPE_CHECKING

from scorer import ScoredProgram

if TYPE_CHECKING:
    from maze_game import Maze
    from misc import VMResult

REWARD_FINISH = 10000
REWARD_UNIQUE_CELL = 50
REWARD_VALID_MOVE = 5
PENALTY_STEP = 1

def grade_maze_performance(result: VMResult, maze: Maze) -> int:
    """
    Assigns a performance score based on how well a program navigated a maze.
    """
    score = 0

    # Big reward for finishing
    if maze.is_finished():
        score += REWARD_FINISH

    # Reward exploration and valid moves, penalize total steps
    score += len(maze.visited_cells) * REWARD_UNIQUE_CELL
    score += maze.valid_moves * REWARD_VALID_MOVE
    score -= maze.total_steps * PENALTY_STEP

    # Penalize errors
    if result.halted :
        score -= 100

    return score