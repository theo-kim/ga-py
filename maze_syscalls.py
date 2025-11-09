from __future__ import annotations
from typing import TYPE_CHECKING, List
from syscalls import Syscall
from bitarray import  bitarray

from misc import MiscVM

if TYPE_CHECKING:
    from misc import Runtime
    from maze_game import Maze

class MoveUpSyscall(Syscall):
    SYSCALL_ID = 0x10
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: Runtime) -> None:
        self.maze.move('w')
        return rt

class MoveDownSyscall(Syscall):
    SYSCALL_ID = 0x11
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: Runtime) -> None:
        self.maze.move('s')
        return rt

class MoveLeftSyscall(Syscall):
    SYSCALL_ID = 0x12
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: Runtime) -> None:
        self.maze.move('a')
        return rt

class MoveRightSyscall(Syscall):
    SYSCALL_ID = 0x13
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: Runtime) -> None:
        self.maze.move('d')
        return rt

class GetFinishPos(Syscall):
    SYSCALL_ID = 0x14
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: Runtime) -> None:
        rt.reg[0].value = bitarray(self.maze.finish_y.to_bytes(MiscVM.WORD_LENGTH / 8, MiscVM.ENDIAN))
        rt.reg[1].value = bitarray(self.maze.finish_x.to_bytes(MiscVM.WORD_LENGTH / 8, MiscVM.ENDIAN))
        return rt

class GetPlayerPos(Syscall):
    SYSCALL_ID = 0x15
    def __init__(self, maze: Maze, **_kwargs):
        self.maze = maze
    def execute(self, rt: Runtime) -> None:
        rt.reg[0].value = bitarray(self.maze.player_y.to_bytes(MiscVM.WORD_LENGTH / 8, MiscVM.ENDIAN))
        rt.reg[1].value = bitarray(self.maze.player_x.to_bytes(MiscVM.WORD_LENGTH / 8, MiscVM.ENDIAN))
        return rt
