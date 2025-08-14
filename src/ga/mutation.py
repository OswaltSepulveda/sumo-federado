import random
from typing import Dict
from .encoding import Individual, TLSGene, PhaseGene

def mutate(ind: Individual, rate: float, time_jitter: float, offset_jitter: float, reorder_prob: float, rng=None):
    rng = rng or random
    for tid, tls in ind.genome.items():
        # offset
        if rng.random() < rate:
            tls.offset += rng.uniform(-offset_jitter, offset_jitter)
        # fases
        for i, ph in enumerate(tls.phases):
            if rng.random() < rate:
                ph.g += rng.uniform(-time_jitter, time_jitter)
            if rng.random() < rate:
                ph.y += rng.uniform(-time_jitter, time_jitter)
            if rng.random() < rate:
                ph.r += rng.uniform(-time_jitter, time_jitter)
        # reordenar fases
        if rng.random() < reorder_prob:
            rng.shuffle(tls.phases)
