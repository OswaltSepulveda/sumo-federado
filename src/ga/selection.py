import random
from typing import List
from .encoding import Individual, clone_individual

def tournament(pop: List[Individual], k=3, rng=None) -> Individual:
    rng = rng or random
    cand = rng.sample(pop, k)
    return max(cand, key=lambda x: x.fitness)

def roulette(pop: List[Individual], rng=None) -> Individual:
    rng = rng or random
    # desplazar fitness si hay negativos
    minfit = min(ind.fitness for ind in pop)
    base = -minfit + 1e-9 if minfit < 0 else 0.0
    total = sum(ind.fitness + base for ind in pop)
    r = rng.uniform(0, total)
    acc = 0.0
    for ind in pop:
        acc += ind.fitness + base
        if acc >= r:
            return ind
    return pop[-1]

def ranking(pop: List[Individual], rng=None) -> Individual:
    rng = rng or random
    sorted_pop = sorted(pop, key=lambda x: x.fitness)
    # pesos lineales por ranking
    weights = list(range(1, len(pop)+1))
    total = sum(weights)
    r = rng.uniform(0, total)
    acc = 0
    for ind, w in zip(sorted_pop, weights):
        acc += w
        if acc >= r:
            return ind
    return sorted_pop[-1]
