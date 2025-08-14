from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
import random
import copy

# Interfaz mínima con tu modelo TLS existente
@dataclass
class PhaseGene:
    active_approaches: List[str]  # p.ej ["A1B1","B1C1"] (1 o 2 según compat)
    g: float
    y: float
    r: float

@dataclass
class TLSGene:
    tls_id: str
    offset: float
    phases: List[PhaseGene]  # orden de fases

@dataclass
class Individual:
    genome: Dict[str, TLSGene]           # tls_id -> TLSGene
    meta: Dict[str, Any] = field(default_factory=dict)
    fitness: float = None

def clone_individual(ind: Individual) -> Individual:
    return Individual(genome=copy.deepcopy(ind.genome), meta=dict(ind.meta), fitness=ind.fitness)

# ---- Helpers de factibilidad (rangos + compatibilidad) ----
@dataclass
class TLSBounds:
    min_green: float
    max_green: float
    min_yellow: float
    max_yellow: float
    min_red: float
    max_red: float
    min_cycle: float
    max_cycle: float

def clamp(v, lo, hi): return max(lo, min(hi, v))

def cycle_time(tls: TLSGene) -> float:
    return sum(p.g + p.y + p.r for p in tls.phases)

def repair_tls(tls: TLSGene, bounds: TLSBounds, compat_groups: List[List[str]] = None) -> Tuple[TLSGene, int]:
    """Ajusta tiempos a rangos y repara violaciones de compatibilidad. Retorna tls reparado y #violaciones detectadas."""
    violations = 0
    # tiempos por fase
    for p in tls.phases:
        p.g = clamp(p.g, bounds.min_green, bounds.max_green)
        p.y = clamp(p.y, bounds.min_yellow, bounds.max_yellow)
        p.r = clamp(p.r, bounds.min_red, bounds.max_red)
        # compatibilidad: si hay más de 1 approach activo, deben pertenecer al mismo grupo
        if compat_groups and len(p.active_approaches) > 1:
            ok = any(set(p.active_approaches).issubset(set(g)) for g in compat_groups)
            if not ok:
                # repara dejando solo la primera aproximación (estrategia conservadora)
                p.active_approaches = [p.active_approaches[0]]
                violations += 1
        # si no hay compat_groups, forzamos “una vía activa”
        if not compat_groups and len(p.active_approaches) > 1:
            p.active_approaches = [p.active_approaches[0]]
            violations += 1
    # ciclo
    cyc = cycle_time(tls)
    if cyc < bounds.min_cycle or cyc > bounds.max_cycle:
        violations += 1
        # normaliza ciclo escalando verdes proporcionalmente
        scale = (bounds.min_cycle + bounds.max_cycle) / 2.0 / max(cyc, 1e-9)
        for p in tls.phases:
            p.g = clamp(p.g * scale, bounds.min_green, bounds.max_green)
        # recalcula por si los clamps forzaron límites
        cyc2 = cycle_time(tls)
        if cyc2 < bounds.min_cycle or cyc2 > bounds.max_cycle:
            violations += 1
    return tls, violations

def repair_individual(ind: Individual, bounds_map: Dict[str, TLSBounds], compat_map: Dict[str, List[List[str]]]) -> int:
    total = 0
    for tid, tls in ind.genome.items():
        b = bounds_map.get(tid) or list(bounds_map.values())[0]  # usa defaults si no hay por-tls
        compat = compat_map.get(tid)
        _, v = repair_tls(tls, b, compat)
        total += v
    return total

# ---- Inicialización ----
def init_individual(tls_blueprint: Dict[str, Dict], rng: random.Random) -> Individual:
    """
    tls_blueprint: tls_id -> dict con:
      - 'offset_range': (lo, hi)
      - 'phases': lista de dicts {'approaches': [...], 'g': (lo,hi), 'y': (lo,hi), 'r': (lo,hi)}
    """
    genome = {}
    for tid, spec in tls_blueprint.items():
        offset_lo, offset_hi = spec.get("offset_range", (0, 30))
        offset = rng.uniform(offset_lo, offset_hi)
        phases = []
        for ph in spec["phases"]:
            g = rng.uniform(*ph["g"])
            y = rng.uniform(*ph["y"])
            r = rng.uniform(*ph["r"])
            phases.append(PhaseGene(active_approaches=list(ph["approaches"]), g=g, y=y, r=r))
        genome[tid] = TLSGene(tls_id=tid, offset=offset, phases=phases)
    return Individual(genome=genome)

def init_population(n: int, tls_blueprint: Dict[str, Dict], seed: int = 42) -> List[Individual]:
    rng = random.Random(seed)
    return [init_individual(tls_blueprint, rng) for _ in range(n)]
