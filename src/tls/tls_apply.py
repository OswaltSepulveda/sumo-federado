# src/tls/tls_model.py
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional, Set
import json, os

# -------- Especificaciones de plan --------

@dataclass
class TLSPhaseSpec:
    """
    Fase lógica: lista de aproximaciones activas simultáneamente + tiempos G/Y/R.
    Si quieres 1 sola vía a la vez, usa una lista de tamaño 1.
    """
    active_approaches: List[str]
    green_s: float
    yellow_s: float
    red_s: float

@dataclass
class TLSPlanSpec:
    """Plan completo para un TLS."""
    tls_id: str
    phases: List[TLSPhaseSpec]
    offset_s: float = 0.0
    program_id: str = "GA_PLAN"

    @property
    def cycle_s(self) -> float:
        return sum(p.green_s + p.yellow_s + p.red_s for p in self.phases)

# -------- Utilidades de mapeo y validación --------

def group_links_by_incoming_edge(controlled_links) -> Dict[int, str]:
    """
    controlled_links = traci.trafficlight.getControlledLinks(tls_id)
    Retorna {link_index -> approach_id} usando el edge entrante (antes del '_').
    """
    mapping: Dict[int, str] = {}
    for idx, conns in enumerate(controlled_links):
        if not conns: 
            continue
        in_lane = conns[0][0]  # ej "B1C1_0"
        approach = in_lane.split('_')[0]  # ej "B1C1"
        mapping[idx] = approach
    return mapping

def _build_state(active_set: Set[str], linkidx_to_approach: Dict[int, str], char: str) -> str:
    L = max(linkidx_to_approach.keys()) + 1 if linkidx_to_approach else 0
    out = []
    for i in range(L):
        ap = linkidx_to_approach.get(i)
        out.append(char if ap in active_set else 'r')
    return "".join(out)

def validate_ranges(plan: TLSPlanSpec,
                    min_green=5.0, max_green=60.0,
                    min_yellow=2.0, max_yellow=5.0,
                    min_red=0.0, max_red=10.0,
                    min_cycle=20.0, max_cycle=240.0) -> None:
    for p in plan.phases:
        if not (min_green <= p.green_s <= max_green):
            raise ValueError(f"Green fuera de rango: {p.green_s}s")
        if not (min_yellow <= p.yellow_s <= max_yellow):
            raise ValueError(f"Yellow fuera de rango: {p.yellow_s}s")
        if not (min_red <= p.red_s <= max_red):
            raise ValueError(f"Red fuera de rango: {p.red_s}s")
    if not (min_cycle <= plan.cycle_s <= max_cycle):
        raise ValueError(f"Ciclo fuera de rango: {plan.cycle_s}s (lim {min_cycle}-{max_cycle})")

def _pairs(s: List[str]) -> Set[Tuple[str, str]]:
    out = set()
    for i in range(len(s)):
        for j in range(i+1, len(s)):
            a,b = s[i], s[j]
            if a > b: a,b = b,a
            out.add((a,b))
    return out

def build_allowed_pairs_from_groups(compat_groups: List[List[str]]) -> Set[Tuple[str, str]]:
    """
    De grupos de compatibilidad (cada grupo es un conjunto de aproximaciones
    que pueden estar activas a la vez) construye todos los pares permitidos.
    """
    allowed: Set[Tuple[str,str]] = set()
    for g in compat_groups:
        allowed |= _pairs(sorted(set(g)))
        # también permite 'pares' (a,a) implícitos con una sola activa:
        for a in g:
            allowed.add((a,a))
    return allowed

def validate_state_compatibility(state: str,
                                 linkidx_to_approach: Dict[int, str],
                                 allowed_pairs: Optional[Set[Tuple[str,str]]]) -> None:
    # Obtén las aproximaciones activas (G/g/y)
    active: List[str] = []
    for i,c in enumerate(state):
        if c in ("G","g","y"):
            ap = linkidx_to_approach.get(i)
            if ap:
                active.append(ap)
    # Si no se definieron pares permitidos: por defecto exigir <=1 activa (enunciado).
    # (Esto respeta “se activa una vía por vez” si no defines compatibilidad) :contentReference[oaicite:2]{index=2}
    if not allowed_pairs:
        if len(set(active)) > 1:
            raise ValueError(f"Violación: múltiples aproximaciones activas sin compatibilidad declarada: {set(active)}")
        return
    # Verifica que todo par activo esté permitido
    for i in range(len(active)):
        for j in range(i+1, len(active)):
            a,b = active[i], active[j]
            if a > b: a,b = b,a
            if (a,b) not in allowed_pairs:
                raise ValueError(f"Par no permitido simultáneamente: {a} & {b}")

def build_program_states(plan: TLSPlanSpec,
                         linkidx_to_approach: Dict[int, str],
                         compat_groups: Optional[List[List[str]]] = None) -> List[Tuple[str, float]]:
    """
    Construye [(state, duration_s), ...] expandiendo cada fase a 3 estados:
    - todos los active_approaches en 'G'
    - luego 'y' (amarillo)
    - luego 'r' (clearance)
    """
    allowed_pairs = build_allowed_pairs_from_groups(compat_groups) if compat_groups else None
    states: List[Tuple[str, float]] = []
    for ph in plan.phases:
        aset = set(ph.active_approaches)
        s_g = _build_state(aset, linkidx_to_approach, 'G')
        s_y = _build_state(aset, linkidx_to_approach, 'y')
        s_r = _build_state(set(), linkidx_to_approach, 'r')
        validate_state_compatibility(s_g, linkidx_to_approach, allowed_pairs)
        validate_state_compatibility(s_y, linkidx_to_approach, allowed_pairs)
        states += [(s_g, ph.green_s), (s_y, ph.yellow_s), (s_r, ph.red_s)]
    return states

# -------- (De)serialización --------

def plan_to_json_dict(plan: TLSPlanSpec) -> Dict:
    return {
        "tls_id": plan.tls_id,
        "program_id": plan.program_id,
        "offset_s": plan.offset_s,
        "phases": [asdict(p) for p in plan.phases],
    }

def save_plan_json(plan: TLSPlanSpec, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan_to_json_dict(plan), f, ensure_ascii=False, indent=2)

def load_plan_json(path: str) -> TLSPlanSpec:
    data = json.load(open(path, "r", encoding="utf-8"))
    phases = [TLSPhaseSpec(**p) for p in data["phases"]]
    return TLSPlanSpec(tls_id=data["tls_id"], program_id=data.get("program_id","GA_PLAN"),
                       offset_s=float(data.get("offset_s",0.0)), phases=phases)
