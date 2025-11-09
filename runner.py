#!/usr/bin/env python3
"""
fuzz_runner_live.py

Generate random byte arrays (16-bit divisible), assemble to 16-bit words,
run them on your MISC VM, and show a live-updating progress bar with
runtime outcome tallies:

- graceful      : EXIT syscall (or SystemExit) -> clean shutdown
- pc_end        : VM returned normally (PC ran off end)
- runtime_error : VM raised RuntimeError
- other_error   : Any other unexpected exception

Usage:
  python3 fuzz_runner_live.py --count 200
  python3 fuzz_runner_live.py --count 200 --fixed-words 8 --endian little
  python3 fuzz_runner_live.py --count 100 --min-words 4 --max-words 64
  python3 fuzz_runner_live.py --count 100 --show-samples 5

No external packages required.
"""

import argparse
import os
import random
import json
import csv
import sys
import multiprocessing
import statistics
try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None
    progress = None

from dataclasses import dataclass
from typing import Dict, List, Literal, Tuple, Any

# --- Your VM must be importable (same directory or PYTHONPATH) ---
from misc import Memory, MiscVM, Endian, VMResult  # noqa: F401
from scorer import ScoredProgram
from maze_game import Maze
from maze_scorer import grade_maze_performance
import maze_syscalls as _m_syscalls
from syscalls import build_systable, OutputStream
from genetics import GeneticAlgo
from bar import RunnerProgress

# ========= Syscalls ==========

def initialize_syscalls(output_stream: OutputStream, maze: Maze | None = None) -> Dict[int, callable]:
        """Initializes all registered syscalls and builds the systable."""
        # This is a bit of a hack to handle two different sets of syscalls.
        # In a larger project, you might use different entry points or config files.
        kwargs = {'stream': output_stream}
        if maze:
            kwargs['maze'] = maze
        return build_systable(**kwargs)

# ========== Assembly helpers ==========

def random_program_bytes(words: int) -> bytes:
    return os.urandom(words * 2)  # 2 bytes per 16-bit word


# ========== VM run wrapper ==========

def run_one(index: int, program_words: List[int], maze: Maze, log: bool = True) -> VMResult:
    """Run a single program"""
    output_stream = OutputStream(log)
    systable = initialize_syscalls(output_stream, maze=maze)

    vm = MiscVM(systable=systable)
    return vm.run(program_words, max_steps=500) # Limit steps per run


# ========== Tally + summary ==========

def summarize(results: List[VMResult]) -> Tuple[Dict[str, int], Dict[str, List[VMResult]]]:
    buckets: Dict[str, int] = {"graceful": 0, "memory": 0, "pc": 0, "other": 0, "opcode": 0, "syscall": 0, "register": 0, "limit": 0}
    by_kind: Dict[str, List[VMResult]] = {k: [] for k in buckets.keys()}
    for r in results:
        kind = "other"
        if not r.halted :
            kind = "graceful"
        if isinstance(r.error, Memory.Error) :
            kind = "memory"
        if isinstance(r.error, MiscVM.Error) :
            if str(r.error) == "Illegal PC access" :
                kind = "pc"
            elif str(r.error).startswith("Unknown opcode") :
                kind = "opcode"
            elif str(r.error) == "Unknown syscall" :
                kind = "syscall"
            elif str(r.error) == "Runtime limit exceeded" :
                kind = "limit" 
            
            buckets[kind] += 1
        by_kind[kind].append(r)
    return buckets, by_kind

# ========== CLI orchestration ==========

def make_lengths(count: int, fixed_words: int | None, min_words: int, max_words: int) -> List[int]:
    if fixed_words is not None:
        return [fixed_words] * count
    return [random.randint(min_words, max_words) for _ in range(count)]

# ========== Genetic Programming ===========

def plot_results(num_generations: int, final_scores: List[int], avg_scores: List[float]):
    """Generates and displays a plot of the GA results."""
    print("\n--- Generating plot... ---")
    generations_x = range(1, num_generations + 1)

    fig, ax = plt.subplots(figsize=(12, 7))

    # 1. Scatter plot for final generation's individual scores
    final_gen_x = [num_generations] * len(final_scores)
    ax.scatter(final_gen_x, final_scores, alpha=0.6, s=30,
               label=f'Final Gen ({num_generations}) Individuals')

    # 2. Line plot for the average score per generation
    ax.plot(generations_x, avg_scores, 'r-o', label='Average Score per Generation')

    # Formatting
    ax.set_title("Genetic Algorithm Performance Over Generations")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Score")
    ax.legend()
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True)) # Ensure integer ticks
    plt.tight_layout()
    plt.show()

# ======== Worker for multiprocessing ========

def process_individual(args_tuple: Tuple[bytes, List[Maze], Endian, bool, int]) -> ScoredProgram:
    """
    Worker function to run a single program and score it.
    Designed to be used with multiprocessing.Pool.
    """
    program_bytes, maze_test_set, endian, log, index = args_tuple

    # Each worker process should have its own random seed.
    random.seed()

    # Select a random maze for this individual
    current_maze = random.choice(maze_test_set)
    current_maze.reset()

    words = program_bytes
    r = run_one(index, words, maze=current_maze, log=log)
    score = grade_maze_performance(r, current_maze)

    return ScoredProgram(score, program_bytes, r)

# ======== Test runtime =========

def test(current_population: List[bytes], maze_test_set: List[Maze], endian: Endian, log: bool, **kwargs: Any) -> List[ScoredProgram]:
    """Run a generational test"""
    # scored_population = [process_individual((program_bytes, maze_test_set, endian, log, i)) for i, program_bytes in enumerate(current_population)]
    tasks = [(program_bytes, maze_test_set, endian, log, i) for i, program_bytes in enumerate(current_population)]

    with multiprocessing.Pool() as pool:
        scored_population = list(pool.imap_unordered(process_individual, tasks))

    return scored_population

def main() -> None:
    ap = argparse.ArgumentParser(description="Fuzz random MISC programs with live progress and tallies.")
    ap.add_argument("--count", type=int, default=50, help="Number of programs to generate and run.")
    ap.add_argument("--fixed-words", type=int, default=None,
                    help="If provided, each program will be exactly this many 16-bit words.")
    ap.add_argument("--min-words", type=int, default=4,
                    help="Minimum number of 16-bit words (ignored if --fixed-words is set).")
    ap.add_argument("--max-words", type=int, default=64,
                    help="Maximum number of 16-bit words (ignored if --fixed-words is set).")
    ap.add_argument("--endian", choices=["big", "little"], default="big",
                    help="Endianness for assembling words from bytes.")
    ap.add_argument("--show-samples", type=int, default=0,
                    help="Print up to N sample results (failures first).")
    ap.add_argument("--no-live", action="store_true",
                    help="Disable live progress/tallies (useful in non-TTY logs).")
    ap.add_argument("--force-live", action="store_true",
                help="Force live progress even if stdout/stderr is not a TTY.")
    ap.add_argument("--generations", type=int, default=1,
                    help="Number of generations to run for the genetic algorithm.")
    ap.add_argument("--mutation-rate", type=float, default=0.001,
                    help="Per-bit mutation rate for offspring (e.g., 0.001).")
    ap.add_argument("--print-output", action="store_true",
                help="Print any characters from the PUTC syscall to stdout.")
    ap.add_argument("--save-population", type=str, default=None,
                    help="File to save the final generation's programs to (in hex format).")
    ap.add_argument("--load-population", type=str, default=None,
                    help="File to load as the initial population (in hex format).")
    ap.add_argument("--plot", action="store_true",
                    help="Show a plot of scores at the end (requires matplotlib).")
    ap.add_argument("--processes", type=int, default=os.cpu_count(),
                    help="Number of processes to use for evaluation. Defaults to all available CPU cores.")
    ap.add_argument("--csv-log", type=str, default=None,
                    help="Path to save a CSV log of all fitness scores per generation.")

    # Maze-specific arguments
    ap.add_argument("--maze-width", type=int, default=15, help="Width of the mazes to generate.")
    ap.add_argument("--maze-height", type=int, default=15, help="Height of the mazes to generate.")

    args = ap.parse_args()

    if args.fixed_words is None and args.min_words > args.max_words:
        ap.error("--min-words cannot be greater than --max-words")

    # --- Initial Population ---
    if args.load_population:
        print(f"--- Loading population and mazes from {args.load_population} ---")
        try:
            with open(args.load_population, 'r') as f:
                data = json.load(f)
            
            # Load population
            hex_population = data.get("population", [])
            if not hex_population:
                ap.error("Population file is missing 'population' list or it is empty.")
            current_population = [bytes.fromhex(p) for p in hex_population]

            # Load mazes
            maze_data = data.get("mazes", [])
            if not maze_data:
                ap.error("Population file is missing 'mazes' list or it is empty.")
            maze_test_set = [Maze(from_data=m_data) for m_data in maze_data]

        except FileNotFoundError:
            ap.error(f"Population file not found: {args.load_population}")
        except ValueError as e:
            ap.error(f"Error decoding data in '{args.load_population}': {e}")
        except json.JSONDecodeError as e:
            ap.error(f"Error parsing JSON from '{args.load_population}': {e}")
    else:
        program_lengths = make_lengths(args.count, args.fixed_words, args.min_words, args.max_words)
        current_population: List[bytes] = [random_program_bytes(wlen) for wlen in program_lengths]
        # --- Maze Test Set ---
        print(f"--- Generating 100 mazes of size {args.maze_width}x{args.maze_height} ---")
        maze_test_set = [Maze(width=args.maze_width, height=args.maze_height) for _ in range(100)]

    generation_avg_scores: List[float] = []
    generation_avg_lengths: List[float] = []

    if args.print_output:
        print("--- Running with PUTC output enabled ---")

    # --- CSV Logging Setup ---
    csv_file = None
    csv_writer = None
    if args.csv_log:
        try:
            # Open the file in write mode, with newline='' to prevent extra blank rows
            csv_file = open(args.csv_log, 'w', newline='')
            csv_writer = csv.writer(csv_file)
            # Write the header
            csv_writer.writerow(['generation', 'score'])
        except IOError as e:
            ap.error(f"Could not open file for CSV logging: {e}")

    def log_scores_to_csv(generation: int, scores: List[int]):
        if csv_writer:
            for score in scores:
                csv_writer.writerow([generation, score])

    print("--- Running genetic algorithm ---")
    bar = RunnerProgress("Running... ", max=args.generations)

    ga = GeneticAlgo(
        mutation_rate=args.mutation_rate,
        crossover_rate=0.8,
        test_func=test,
        hook_next_gen=bar.next_generation,
        hook_finished=bar.finish,
        hook_reproduction=bar.perform_reproduction,
        hook_selection=bar.perform_selection,
        hook_log_scores=log_scores_to_csv,
    )

    scored_population = ga.run(
        current_population,
        args.generations,
        log=not args.no_live,
        maze_test_set=maze_test_set,
        endian=args.endian
    )

    # Clean up CSV file handle
    if csv_file:
        csv_file.close()

    if args.print_output:
        print("--- End of PUTC output ---")

    # --- Final Summary ---
    final_gen_results = [sp.result for sp in scored_population]
    final_gen_scores = [sp.score for sp in scored_population]
    totals, by_kind = summarize(final_gen_results)

    if final_gen_scores:
        total_score = sum(final_gen_scores)
        quartiles = statistics.quantiles(final_gen_scores, n=4) if len(final_gen_scores) > 1 else [0,0,0]

        print(f"\nTotal Score: {total_score}")
        print("=== Score Statistics (Final Generation) ===")
        print(f"Min Score    : {min(final_gen_scores)}")
        print(f"Max Score    : {max(final_gen_scores)}")
        print(f"Average Score: {statistics.mean(final_gen_scores):.2f}")
        print(f"Median Score : {statistics.median(final_gen_scores)}")
        print(f"Range        : {max(final_gen_scores) - min(final_gen_scores)}")
        print(f"Quartiles (Q1, Q2, Q3): {quartiles[0]}, {quartiles[1]}, {quartiles[2]}")

    if generation_avg_scores:
        print("\n=== Average Score per Generation ===")
        for i, avg_score in enumerate(generation_avg_scores, 1):
            print(f"Generation {i:2d}: {avg_score:.2f}")

    if generation_avg_lengths:
        print("\n=== Average Program Length (bytes) per Generation ===")
        for i, avg_length in enumerate(generation_avg_lengths, 1):
            print(f"Generation {i:2d}: {avg_length:.2f}")

    # --- Save Final Population ---
    if args.save_population:
        print(f"\n--- Saving final generation and mazes to {args.save_population} ---")
        # scored_population is sorted by score, descending. Best is at index 0.
        save_data = {
            "best_program_hex": scored_population[0].program_bytes.hex(),
            "population": [p.program_bytes.hex() for p in scored_population],
            "mazes": [m.to_dict() for m in maze_test_set]
        }
        try:
            with open(args.save_population, 'w') as f:
                json.dump(save_data, f, indent=2)
        except Exception as e:
            print(f"Error saving population file: {e}", file=sys.stderr)

    # --- Plotting ---
    if args.plot:
        if plt is None:
            print("\n--- Plotting skipped: matplotlib is not installed. ---", file=sys.stderr)
            print("--- To install, run: pip install matplotlib ---", file=sys.stderr)
        elif generation_avg_scores and final_gen_scores:
            plot_results(args.generations, final_gen_scores, generation_avg_scores)

    print("=== Run Summary ===")
    for k in totals.keys():
        print(f"{k:14s}: {totals[k]}")


if __name__ == "__main__":
    main()
