from __future__ import annotations

import random
from statistics import mean
import numpy as np
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple
import bitarray

from scorer import ScoredProgram
if TYPE_CHECKING:
    from misc import Endian

def _normalize_data(data):
    if len(set(data)) == 1 :
        return [1] * len(data)
    return ((data - np.min(data)) / (np.max(data) - np.min(data))).tolist()

class GeneticAlgo() :
    def __init__(
                self, 
                mutation_rate: float, 
                crossover_rate: float,
                test_func: Callable[[List[bytes]], ScoredProgram],
                hook_next_gen: Callable[[int], None] = lambda _ : None,
                hook_finished: Callable[[], None] = lambda _ : None,
                hook_selection: Callable[[float], None] = lambda _ : None,
                hook_reproduction: Callable[[], None] = lambda _ : None,
                hook_log_scores: Callable[[int, List[int]], None] = lambda _, __ : None,
                endian: Endian = "little",
                **kwargs # additional variables to pass to the test function    
            ) :
        self.point_mutation_rate = mutation_rate
        self.large_mutation_rate = mutation_rate
        self.chromosomal_mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.test_func = test_func
        self.hook_next_gen = hook_next_gen
        self.hook_finished = hook_finished
        self.hook_selection = hook_selection
        self.hook_reproduction = hook_reproduction
        self.hook_log_scores = hook_log_scores
        self.endian = endian
        self.kwargs = kwargs

    def _crossover(self, p1_bytes: bytes, p2_bytes: bytes) -> Tuple[bytes, bytes]:
        """Performs single-point crossover on two parent byte strings."""
        if random.random() > self.crossover_rate :
            return p1_bytes, p2_bytes
        crossover = random.randint(0, min(len(p1_bytes), len(p2_bytes)) // 2) * 2
        children = (
            p1_bytes[:crossover] + p2_bytes[crossover:],
            p2_bytes[:crossover] + p1_bytes[crossover:],
        )
        return children

    def _point_mutate(self, bits: bitarray.bitarray, idx: int) -> bitarray.bitarray:
        """Applies bit-flip mutation to a bit array"""
        bits.invert(idx)
        return bits
    
    def _insert_mutate(self, bits: bitarray.bitarray, idx: int, proportion: float = 0.5) -> bitarray.bitarray :
        """Applies bit insertion mutation to a bit array. Will randomly select 1 or 0"""
        bits.insert(idx, 0 if random.random() < proportion else 1)
        return bits
    
    def _delete_mutate(self, bits: bitarray.bitarray, idx: int) -> bitarray.bitarray :
        """Applies deletion mutation to bit array (delete selected bit)"""
        bits.pop(idx)
        return bits

    def _mutate(self, program_bytes: bytes) -> bytes:
        """Applies bit-flip mutation to a byte string."""
        if self.point_mutation_rate == 0:
            return program_bytes
        
        mutated_bits = bitarray.bitarray(program_bytes, endian=self.endian)
        
        i = 0
        while i < len(mutated_bits) : 
            if random.random() < self.point_mutation_rate :
                mutated_bits = self._point_mutate(mutated_bits, i)
                mutate_type = random.choice([0, 1, 2])
                if mutate_type == 0 :
                    mutated_bits = self._point_mutate(mutated_bits, i)
                elif mutate_type == 1 :
                    mutated_bits = self._insert_mutate(mutated_bits, i)
                    i += 1
                elif mutate_type == 2 :
                    mutated_bits = self._delete_mutate(mutated_bits, i)
                    i -= 1
            i += 1
                
        return mutated_bits.tobytes()

    def _select(self, scored_population: List[ScoredProgram]) -> list[tuple[bytes, bytes]] :
        """Select which individuals to allow to reproduce and pair them off"""
        normalized_scores = _normalize_data([s.score for s in scored_population])
        p1 = random.choices(scored_population, weights=normalized_scores, k=len(scored_population) // 2)
        p2 = random.choices(scored_population, weights=normalized_scores, k=len(scored_population) // 2)
        return [ (x.program_bytes, y.program_bytes) for x, y in zip(p1, p2) ]

    def run(
                self,
                population: List[bytes], 
                total_generations: int = 0, 
                exit_criteria: Optional[Callable[[List[Any], int], bool]] = None,
                **kwargs # additional variables to pass to the test function
            ) :
        """Runs a single generation of programs and returns their scores."""
        additional_vars = { **self.kwargs, **kwargs }

        if exit_criteria is None :
            if total_generations == 0 :
                raise ValueError("You must specify either a total number of generations or an exit criteria")
            exit_criteria = lambda _, gen : gen + 1 >= total_generations
        
        current_generation = 0
        scored_population: List[ScoredProgram] = []

        while True:
            self.hook_next_gen(current_generation)
            scored_population = self.test_func(population, **additional_vars)
            scores = [s.score for s in scored_population]
            self.hook_log_scores(current_generation, scores)
            if exit_criteria(population, current_generation) :
                self.hook_finished()
                break
            self.hook_selection(mean(scores))
            survivors = self._select(scored_population)
            self.hook_reproduction()
            # Create children, mutate them, and flatten the resulting list of pairs
            # into a single list for the next generation.
            population = [ self._mutate(child) 
                           for p1, p2 in survivors 
                           for child in self._crossover(p1, p2) ]
            current_generation += 1
        
        return scored_population
