#!/usr/bin/env python3
"""
visualize_run.py

Load a saved JSON run file and step through the execution of the
best-performing program on one of the saved mazes.

Usage:
  python3 visualize_run.py <path_to_run_file.json>
"""

import argparse
import json
import os
import sys
from typing import Tuple
from bitarray import bitarray
from bitarray.util import ba2int

from maze_game import Maze, WALL, FLOOR
from misc import MiscVM, Runtime
from runner import initialize_syscalls, OutputStream

# Maze symbols for rendering
PLAYER_CHAR = 'P'
FINISH_CHAR = 'F'

def clear_screen():
    """Clears the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def render_maze(maze: Maze):
    """Renders the current state of the maze to the console."""
    grid_copy = [list(row) for row in maze.grid]

    # Place finish marker
    if grid_copy[maze.finish_y][maze.finish_x] == FLOOR:
        grid_copy[maze.finish_y][maze.finish_x] = FINISH_CHAR

    # Place player marker
    if grid_copy[maze.player_y][maze.player_x] == FLOOR or grid_copy[maze.player_y][maze.player_x] == FINISH_CHAR:
        grid_copy[maze.player_y][maze.player_x] = PLAYER_CHAR

    for row in grid_copy:
        print("".join(row))

def disassemble(program: bytes, pc: int) -> Tuple[str, int]:
    """Disassembles one instruction at pc. Returns (text, instruction_length_in_bytes)."""
    if pc + MiscVM.INSTRUCTION_LENGTH > len(program):
        return ("(incomplete)", MiscVM.INSTRUCTION_LENGTH)

    instruction_bytes = program[pc : pc + MiscVM.INSTRUCTION_LENGTH]
    instruction_bits = bitarray(endian="big")
    instruction_bits.frombytes(instruction_bytes)

    op_code_val = ba2int(instruction_bits[:MiscVM.OP_LEN])
    op_code_bytes = op_code_val.to_bytes(1, 'big')

    for name, op_bytes, arg_type, _, _, _ in MiscVM.OPS:
        if op_code_bytes == op_bytes:
            mnemonic = name.split('_', 1)[1]
            line = f"{mnemonic:<18}"

            if arg_type == MiscVM.OpArg.I:
                i = ba2int(instruction_bits[MiscVM.OP_LEN:], signed=True)
                line += f"{i}"
            elif arg_type == MiscVM.OpArg.RI:
                r_d = ba2int(instruction_bits[MiscVM.OP_LEN : MiscVM.OP_LEN + MiscVM.REG_LEN])
                i = ba2int(instruction_bits[MiscVM.OP_LEN + MiscVM.REG_LEN:], signed=True)
                line += f"r{r_d}, {i}"
            elif arg_type == MiscVM.OpArg.RRI:
                r_d = ba2int(instruction_bits[MiscVM.OP_LEN : MiscVM.OP_LEN + MiscVM.REG_LEN])
                r_s = ba2int(instruction_bits[MiscVM.OP_LEN + MiscVM.REG_LEN : MiscVM.OP_LEN + MiscVM.REG_LEN * 2])
                i = ba2int(instruction_bits[MiscVM.OP_LEN + MiscVM.REG_LEN * 2:], signed=True)
                line += f"r{r_d}, r{r_s}, {i}"
            return (line, MiscVM.INSTRUCTION_LENGTH)

    return (f"DB 0x{instruction_bytes.hex()}", MiscVM.INSTRUCTION_LENGTH)


def main():
    parser = argparse.ArgumentParser(description="Step-through visualizer for maze-solving programs.")
    parser.add_argument('run_file', help="Path to the JSON run file saved by runner.py.")
    args = parser.parse_args()

    # --- Load Data ---
    try:
        with open(args.run_file, 'r') as f:
            data = json.load(f)
        
        best_program_hex = data['best_program_hex']
        program_bytes = bytes.fromhex(best_program_hex)

        mazes_data = data['mazes']
        maze_test_set = [Maze(from_data=m_data) for m_data in mazes_data]
        print(f"Loaded best program ({len(program_bytes)} bytes) and {len(maze_test_set)} mazes.")

    except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        print(f"Error loading or parsing file '{args.run_file}': {e}", file=sys.stderr)
        sys.exit(1)

    # --- Maze Selection ---
    maze_to_run = None
    while maze_to_run is None:
        try:
            val = input(f"Select a maze to run (0-{len(maze_test_set)-1}): ")
            maze_index = int(val)
            if 0 <= maze_index < len(maze_test_set):
                maze_to_run = maze_test_set[maze_index]
                maze_to_run.reset() # Ensure maze is in its initial state
            else:
                print("Index out of range.")
        except (ValueError, KeyboardInterrupt):
            print("\nInvalid input or exiting.")
            sys.exit(0)

    # --- VM and Syscall Setup ---
    output_stream = OutputStream(echo=True)
    systable = initialize_syscalls(output_stream, maze=maze_to_run)
    vm = MiscVM(systable=systable)

    try:
        for rt, instr_text in vm.run_debug(program_bytes, max_steps=1000):
            pc = rt.pc
            clear_screen()
            print("--- Maze State ---")
            render_maze(maze_to_run)
            print("\n--- VM State ---")
            reg_strs = []
            print(rt)

            print("\n--- Program Context ---")
            # Show instructions around the current one
            current_addr = 0
            while current_addr < len(program_bytes):
                if abs(current_addr - pc) < 12: # Show instructions in a small window around PC
                    prefix = " -> " if current_addr == pc else "    "
                    disassembled_inst, inst_len = disassemble(program_bytes, current_addr)
                    print(f"{current_addr:04X}:{prefix}{disassembled_inst}")
                else:
                    _, inst_len = disassemble(program_bytes, current_addr)
                current_addr += inst_len
            # Wait for user input
            key = input("Press Enter to step, 'q' to quit... ")
            if key.lower() == 'q':
                break
    except KeyboardInterrupt:
        clear_screen()
    except MiscVM.Stop as e:
        clear_screen()
        print(f"\n--- GRACEFUL EXIT with code {e.code} ---")
    except MiscVM.Error as e:
        clear_screen()
        print(f"\n--- VM ERROR: {e} ---")
    except Exception as e:
        clear_screen()
        print(f"\n--- UNEXPECTED ERROR: {e} ---")

    # --- Final State ---
    print("--- FINAL MAZE STATE ---")
    render_maze(maze_to_run)
    print("\n--- FINAL VM STATE ---")
    reg_strs = []
    for i, v in enumerate(vm.registers):
        reg_name = f"R{i}(RIP)" if i == vm.RIP_REG else f"R{i}"
        reg_strs.append(f"{reg_name}:{v.unsigned:02X}")
    print(f"PC: {vm.pc:04X} | Steps: {maze_to_run.total_steps} | Registers: {' | '.join(reg_strs)}")
    if maze_to_run.is_finished():
        print("\n🎉 The program reached the finish! 🎉")
    else:
        print("\nProgram finished without reaching the end.")

if __name__ == "__main__":
    main()