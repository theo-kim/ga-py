from __future__ import annotations
import ctypes
from typing import TYPE_CHECKING
from syscalls import Syscall

if TYPE_CHECKING:
    from misc import VMState
    from maze_game import Maze

class MoveUpSyscall(Syscall):
    SYSCALL_ID = 0x10
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: VMState) -> None:
        self.maze.move('w')
        return rt

class MoveDownSyscall(Syscall):
    SYSCALL_ID = 0x11
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: VMState) -> None:
        self.maze.move('s')
        return rt

class MoveLeftSyscall(Syscall):
    SYSCALL_ID = 0x12
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: VMState) -> None:
        self.maze.move('a')
        return rt

class MoveRightSyscall(Syscall):
    SYSCALL_ID = 0x13
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: VMState) -> None:
        self.maze.move('d')
        return rt

class GetFinishPos(Syscall):
    SYSCALL_ID = 0x14
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: VMState) -> None:
        rt.registers[0] = ctypes.c_uint8(self.maze.finish_y)
        rt.registers[1] = ctypes.c_uint8(self.maze.finish_x)
        return rt

class GetPlayerPos(Syscall):
    SYSCALL_ID = 0x15
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: VMState) -> None:
        rt.registers[0] = ctypes.c_uint8(self.maze.player_y)
        rt.registers[1] = ctypes.c_uint8(self.maze.player_x)
        return rt
