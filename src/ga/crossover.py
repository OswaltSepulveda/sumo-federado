import random
from typing import Tuple
from .encoding import Individual, TLSGene, PhaseGene, clone_individual

def per_intersection_cx(a: Individual, b: Individual, rng=None) -> Tuple[Individual, Individual]:
    rng = rng or random
    ca, cb = clone_individual(a), clone_individual(b)
    for tid in ca.genome.keys():
        if rng.random() < 0.5:
            ca.genome[tid], cb.genome[tid] = cb.genome[tid], ca.genome[tid]
    return ca, cb

def intra_intersection_cx(a: Individual, b: Individual, swap_frac=0.5, rng=None) -> Tuple[Individual, Individual]:
    rng = rng or random
    ca, cb = clone_individual(a), clone_individual(b)
    for tid in ca.genome.keys():
        pa, pb = ca.genome[tid].phases, cb.genome[tid].phases
        # intercambia algunas fases
        for i in range(min(len(pa), len(pb))):
            if rng.random() < swap_frac:
                pa[i], pb[i] = pb[i], pa[i]
        # mezcla offsets
        if rng.random() < 0.5:
            ca.genome[tid].offset, cb.genome[tid].offset = cb.genome[tid].offset, ca.genome[tid].offset
    return ca, cb
