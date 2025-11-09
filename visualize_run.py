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
from typing import List

from maze_game import Maze, WALL, FLOOR
from misc import MiscVM, DBG
import maze_syscalls as _m_syscalls
from runner import assemble_words_from_bytes, initialize_syscalls, OutputStream
from syscalls import GracefulExit

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

def disassemble(program: List[int], pc: int) -> Tuple[str, int]:
    """Disassembles one instruction at pc. Returns (text, instruction_length_in_bytes)."""
    length = 3 # All instructions are now 3 bytes
    op_map = {
        0x00: "NOP", 0x01: "SYSCALL",
        0x10: "MOV", 0x11: "MOV",
        0x20: "LD", 0x21: "ST",
        0x30: "ADD", 0x31: "SUB", 0x32: "AND",
        0x33: "OR", 0x34: "XOR", 0x35: "NOT",
        0x40: "JMP", 0x41: "JZ"
    }
    
    op = program[pc]
    if op not in op_map:
        return (f"DB 0x{op:02X}", 1)

    name = op_map[op]

    if pc + 3 > len(program):
        return (f"{name} (incomplete)", length)

    arg1, arg2 = program[pc+1], program[pc+2]

    if op == 0x00: # NOP
        return (f"NOP", length)
    elif op == 0x01: # SYSCALL imm
        return (f"SYSCALL {arg1}", length)
    elif op == 0x10: # MOV reg, imm
        return (f"MOV R{arg1}, 0x{arg2:02X}", length)
    elif op == 0x11: # MOV reg, reg
        return (f"MOV R{arg1}, R{arg2}", length)
    elif op == 0x20: # LD reg, [reg]
        return (f"LD R{arg1}, [R{arg2}]", length)
    elif op == 0x21: # ST [reg], reg
        return (f"ST [R{arg1}], R{arg2}", length)
    elif op in [0x30, 0x31, 0x32, 0x33, 0x34]: # ADD/SUB/AND/OR/XOR reg, reg
        return (f"{name} R{arg1}, R{arg2}", length)
    elif op == 0x35: # NOT reg
        return (f"NOT R{arg1}", length)
    elif op == 0x40: # JMP reg
        return (f"JMP R{arg1}", length)
    elif op == 0x41: # JZ reg, reg
        return (f"JZ R{arg1}, R{arg2}", length)

    return (name, length)


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
        program = list(program_bytes)

        mazes_data = data['mazes']
        maze_test_set = [Maze(from_data=m_data) for m_data in mazes_data]
        print(f"Loaded best program ({len(program)} bytes) and {len(maze_test_set)} mazes.")

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
    vm = MiscVM()
    output_stream = OutputStream(echo=True)
    systable = initialize_syscalls(output_stream, maze=maze_to_run)

    try :
        for pc in vm.run(program, systable, max_steps=500, debug=True):
            clear_screen()
            print("--- Maze State ---")
            render_maze(maze_to_run)
            print("\n--- VM State ---")
            reg_strs = []
            for i, v in enumerate(vm.registers):
                reg_strs.append(f"R{i}(RIP):{v:02X}" if i == vm.RIP_REG else f"R{i}:{v:02X}")
            print(f"Steps: {maze_to_run.total_steps} | Registers: {' | '.join(reg_strs)}")

            print("\n--- Program Context ---")
            # Show instructions around the current one
            current_addr = 0
            while current_addr < len(program):
                if abs(current_addr - pc) < 8: # Show instructions in a small window around PC
                    prefix = " -> " if current_addr == pc else "    "
                    disassembled_inst, inst_len = disassemble(program, current_addr)
                    print(f"{current_addr:02X}:{prefix}{disassembled_inst}")
                _, inst_len = disassemble(program, current_addr)
                current_addr += inst_len
            # Wait for user input
            key = input("Press Enter to step, 'q' to quit... ")
            if key.lower() == 'q':
                break
    except KeyboardInterrupt:
        clear_screen()
    except GracefulExit as ge:
        clear_screen()
        print(f"\n--- GRACEFUL EXIT with code {ge.code} ---")
    except RuntimeError as re:
        clear_screen()
        print(f"\n--- RUNTIME ERROR: {re} ---")
    except Exception as e:
        clear_screen()
        print(f"\n--- UNEXPECTED ERROR: {e} ---")

    # --- Final State ---
    print("--- FINAL MAZE STATE ---")
    render_maze(maze_to_run)
    print("\n--- FINAL VM STATE ---")
    reg_strs = []
    for i, v in enumerate(vm.registers):
        reg_strs.append(f"R{i}(RIP):{v:02X}" if i == vm.RIP_REG else f"R{i}:{v:02X}")
    print(f"Steps: {maze_to_run.total_steps} | Registers: {' | '.join(reg_strs)}")
    if maze_to_run.is_finished():
        print("\n🎉 The program reached the finish! 🎉")
    else:
        print("\nProgram finished without reaching the end.")

if __name__ == "__main__":
    main()