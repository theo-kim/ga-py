from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from misc import VMResult

@dataclass
class ScoredProgram:
    score: int
    program_bytes: bytes
    result: VMResult


def grade_performance(result: VMResult) -> int:
    """V
    Assigns a performance score to a single VM run result.

    - Base score is 0.
    - Graceful exit: +100 points.
    - Each character printed via syscall: +100 points.
    - Runtime error: -100 points.
    - Other errors: -200 points.
    - PC ran off end: 0 points.
    """
    score = 0
    if result.outcome == "graceful":
        score += 10
    elif result.outcome == "runtime_error":
        score -= 100
    elif result.outcome == "other_error":
        score -= 200

    score += (result.output_len or 0) * 100

    return score