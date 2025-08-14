# src/tls/tls_apply.py
import os
import sys
import json
import argparse
import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Any

# YAML es opcional (para --plan-yaml / --scenario-yaml)
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


def ensure_traci_on_path():
    sh = os.environ.get("SUMO_HOME")
    if not sh:
        raise EnvironmentError("SUMO_HOME no está definido")
    tools = os.path.join(sh, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)


def parse_cfg(cfg_path: str) -> str:
    """
    Devuelve la ruta del net-file desde un .sumocfg (admite estilos value=...).
    """
    root = ET.parse(cfg_path).getroot()
    # <configuration><input><net-file value="..."/>
    for inp in root.findall("input"):
        nf = inp.get("net-file")
        if nf:
            return nf
        for nf2 in inp.findall("net-file"):
            v = nf2.get("value")
            if v:
                return v
    # legado
    nf = root.get("net-file")
    if nf:
        return nf
    raise RuntimeError("No se encontró net-file en el .sumocfg")


# =========================
# Sanitizers y utilidades
# =========================

def _quantize(t: float, q: float = 0.5) -> float:
    # cuantiza a múltiplos de q segundos
    return round(float(t) / q) * q


def _clamp(t: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(t)))


def _sanitize_phase_times(ph, limits: Dict[str, float], q: float = 0.5):
    # Asegura tiempos dentro de límites + cuantización
    ph.green_s  = _quantize(_clamp(ph.green_s,  limits.get("min_green", 5.0),  limits.get("max_green", 60.0)), q)
    ph.yellow_s = _quantize(_clamp(ph.yellow_s, limits.get("min_yellow", 2.0), limits.get("max_yellow", 5.0)),  q)
    ph.red_s    = _quantize(_clamp(ph.red_s,    limits.get("min_red", 0.0),    limits.get("max_red", 10.0)),   q)
    return ph


def _enforce_single_approach(ph):
    # Seguridad: una sola vía activa por fase (evita "unsafe green")
    if hasattr(ph, "active_approaches") and ph.active_approaches:
        if len(ph.active_approaches) > 1:
            # Conserva solo la primera aproximación (política mínima viable)
            ph.active_approaches = [ph.active_approaches[0]]
    return ph


def _sanitize_plan_spec(phases, offset_s: float, limits: Dict[str, float], q: float = 0.5):
    # Sanea todas las fases y normaliza offset luego
    total_cycle = 0.0
    new_phases = []
    for ph in phases:
        ph = _enforce_single_approach(ph)
        ph = _sanitize_phase_times(ph, limits, q)
        new_phases.append(ph)
        total_cycle += (ph.green_s + ph.yellow_s + ph.red_s)

    # Ajuste de ciclo si excede límites (preferimos recortar ROJO de la última fase)
    min_cycle = limits.get("min_cycle", 20.0)
    max_cycle = limits.get("max_cycle", 240.0)
    # cuantiza total
    total_cycle = _quantize(total_cycle, q)
    if total_cycle < min_cycle and len(new_phases) > 0:
        # incrementa rojo de la última fase para alcanzar min_cycle
        delta = min_cycle - total_cycle
        new_phases[-1].red_s = _quantize(new_phases[-1].red_s + delta, q)
        total_cycle = min_cycle
    elif total_cycle > max_cycle and len(new_phases) > 0:
        # reduce rojo de la última fase hasta max_cycle (sin romper min_red)
        delta = total_cycle - max_cycle
        min_red = limits.get("min_red", 0.0)
        new_red = max(min_red, new_phases[-1].red_s - delta)
        new_phases[-1].red_s = _quantize(new_red, q)
        # recomputa ciclo
        total_cycle = 0.0
        for ph in new_phases:
            total_cycle += (ph.green_s + ph.yellow_s + ph.red_s)
        total_cycle = _quantize(total_cycle, q)

    # Offset normalizado al ciclo (evita offsets mayores al ciclo)
    off = float(offset_s)
    if total_cycle > 0.0:
        off = off % total_cycle
        off = _quantize(off, q)
    else:
        off = 0.0
    return new_phases, off


# =========================
# Helpers para aplicar plan
# =========================

def _apply_plan_for_tls(
    traci,
    tid: str,
    mapping: Dict[int, str],
    plan_spec: Dict[str, Any],
    limits: Dict[str, float],
    compat_groups_for_tid: List[List[str]] = None,
):
    """
    Aplica a un TLS específico el 'plan_spec' con formato:
      {
        "offset": float,
        "phases": [
          {"active_approaches": [str,...], "g": float, "y": float, "r": float},
          ...
        ]
      }
    Usa TLSPhaseSpec/TLSPlanSpec/validate_ranges/build_program_states definidos en tls_model.
    """
    from tls_model import TLSPhaseSpec, TLSPlanSpec, validate_ranges, build_program_states
    from traci import trafficlight as tl

    phases = []
    for ph in plan_spec.get("phases", []):
        phases.append(
            TLSPhaseSpec(
                active_approaches=list(ph.get("active_approaches", [])),
                green_s=float(ph.get("g", 12.0)),
                yellow_s=float(ph.get("y", 3.0)),
                red_s=float(ph.get("r", 1.0)),
            )
        )
    offset = float(plan_spec.get("offset", 0.0))
    plan = TLSPlanSpec(tls_id=tid, phases=phases, offset_s=offset)

    # === NUEVO: sanear fases y offset antes de validar ===
    phases_sane, off_sane = _sanitize_plan_spec(plan.phases, plan.offset_s, limits, q=0.5)
    plan.phases = phases_sane
    plan.offset_s = off_sane
    # ======================================================

    # Validaciones de rangos
    validate_ranges(
        plan,
        min_green=limits.get("min_green", 5.0),
        max_green=limits.get("max_green", 60.0),
        min_yellow=limits.get("min_yellow", 2.0),
        max_yellow=limits.get("max_yellow", 5.0),
        min_red=limits.get("min_red", 0.0),
        max_red=limits.get("max_red", 10.0),
        min_cycle=limits.get("min_cycle", 20.0),
        max_cycle=limits.get("max_cycle", 240.0),
    )

    # Estados y aplicación (¡ahora con compatibilidad!)
    states = build_program_states(
        plan,
        mapping,
        compat_groups=compat_groups_for_tid  # puede ser None (forzará 1 vía activa en tu tls_model)
    )  # [(state, dur), ...]

    phases_traci = [tl.Phase(dur, st) for (st, dur) in states]
    logic = tl.Logic(plan.program_id, 0, 0, phases_traci)
    traci.trafficlight.setCompleteRedYellowGreenDefinition(tid, logic)
    traci.trafficlight.setProgram(tid, plan.program_id)

    # Offset
    cycle = plan.cycle_s
    off = plan.offset_s % cycle if cycle > 0 else 0.0
    acc = 0.0
    phase_index = 0
    remaining = phases_traci[0].duration
    for i, ph in enumerate(phases_traci):
        if acc + ph.duration > off:
            phase_index = i
            remaining = ph.duration - (off - acc)
            break
        acc += ph.duration
    traci.trafficlight.setPhase(tid, phase_index)
    traci.trafficlight.setPhaseDuration(tid, remaining)
    print(
        f">> {tid}: aplicado plan '{plan.program_id}' ciclo={cycle:.1f}s "
        f"offset={off:.1f}s (fase={phase_index}, restante={remaining:.1f}s)"
    )


def apply_plan_from_dict(
    cfg_path: str,
    plan_dict: dict,
    steps: int = 0,
    use_gui: bool = False,
    save_json_dir: str = None,
    limits_override: dict = None,
    compat_map: Dict[str, List[List[str]]] = None,
):
    """
    Punto de entrada que usará el GA.

      - cfg_path: ruta al .sumocfg
      - plan_dict: { "tls": { tls_id: { "offset": ..., "phases":[...] }, ... } }
      - steps: steps a simular tras aplicar (0 = solo aplicar)
      - use_gui: usar sumo-gui si True
      - save_json_dir: si se da, guarda applied_plan.json ahí
      - limits_override: dict opcional con min/max de verdes/amarillos/rojos/ciclo
      - compat_map: dict opcional { tls_id: [ [ap1, ap2], [ap3, ap4], ... ] }
    """
    ensure_traci_on_path()
    import traci
    from tls_model import group_links_by_incoming_edge

    if save_json_dir:
        os.makedirs(save_json_dir, exist_ok=True)
        with open(
            os.path.join(save_json_dir, "applied_plan.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(plan_dict, f, ensure_ascii=False, indent=2)

    limits = limits_override or {}
    bin_name = "sumo-gui" if use_gui else "sumo"
    cmd = [bin_name, "-c", cfg_path, "--no-step-log", "true", "--duration-log.disable", "true"]
    print(">> SUMO:", " ".join(cmd))
    traci.start(cmd)

    try:
        tls_ids = list(traci.trafficlight.getIDList())
        if not tls_ids:
            print(">> No hay semáforos (TLS) en esta red.")
            return

        # Construir mapping por TLS
        tls_maps = {}
        for tid in tls_ids:
            links = traci.trafficlight.getControlledLinks(tid)
            tls_maps[tid] = group_links_by_incoming_edge(links)

        plan_tls = (plan_dict or {}).get("tls", {})
        for tid, spec in plan_tls.items():
            if tid not in tls_maps:
                print(f">> Aviso: TLS '{tid}' no existe en esta red; se omite.")
                continue
            cg = compat_map.get(tid) if compat_map else None
            _apply_plan_for_tls(traci, tid, tls_maps[tid], spec, limits, compat_groups_for_tid=cg)

        # Avanza simulación si se pidió
        for step in range(int(steps)):
            traci.simulationStep()
            if step % 100 == 0:
                print("step=", step)
        print(">> OK: Plan aplicado desde dict.")
    finally:
        traci.close(False)


# =========================
# CLI original + extensiones
# =========================

def _compat_map_from_scenario_yaml(path: str) -> Dict[str, List[List[str]]]:
    """
    Lee un YAML de escenario (configs/scenarios/*.yaml) y extrae:
      tls -> <tls_id> -> compatibility_groups: [...]
    """
    if not path:
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML no está instalado y se solicitó --scenario-yaml")
    data = yaml.safe_load(open(path, "r", encoding="utf-8"))
    result = {}
    for tid, spec in (data.get("tls") or {}).items():
        if "compatibility_groups" in spec:
            result[tid] = spec["compatibility_groups"]
    return result


def main():
    ap = argparse.ArgumentParser(
        description="TLS: inspección/aplicación de plan (una aproximación a la vez o desde JSON/YAML)."
    )
    ap.add_argument("--cfg", required=True, help="Ruta a .sumocfg")

    # Defaults para plan simple (fallback)
    ap.add_argument("--green", type=float, default=12.0)
    ap.add_argument("--yellow", type=float, default=3.0)
    ap.add_argument("--red", type=float, default=1.0)
    ap.add_argument("--offset", type=float, default=0.0, help="Desfase inicial del ciclo (s)")

    # Límites
    ap.add_argument("--min-green", type=float, default=5.0)
    ap.add_argument("--max-green", type=float, default=60.0)
    ap.add_argument("--min-yellow", type=float, default=2.0)
    ap.add_argument("--max-yellow", type=float, default=5.0)
    ap.add_argument("--min-red", type=float, default=0.0)
    ap.add_argument("--max-red", type=float, default=10.0)
    ap.add_argument("--min-cycle", type=float, default=20.0)
    ap.add_argument("--max-cycle", type=float, default=240.0)

    # Nuevos atajos CLI para planes externos y compatibilidad
    ap.add_argument("--plan-json", help="Ruta a plan TLS en JSON")
    ap.add_argument("--plan-yaml", help="Ruta a plan TLS en YAML")
    ap.add_argument("--scenario-yaml", help="YAML de escenario para extraer compatibility_groups")
    ap.add_argument("--save-json-dir", help="Guardar copia del plan aplicado en esta carpeta")

    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--steps", type=int, default=900)
    ap.add_argument("--inspect-only", action="store_true", help="Solo listar TLS y aproximaciones")
    args = ap.parse_args()

    # Si nos pasaron un plan por archivo, usamos el nuevo flujo y salimos
    if args.plan_json or args.plan_yaml:
        if args.plan_json:
            plan = json.load(open(args.plan_json, "r", encoding="utf-8"))
        else:
            if yaml is None:
                raise RuntimeError("PyYAML no está instalado y se solicitó --plan-yaml")
            plan = yaml.safe_load(open(args.plan_yaml, "r", encoding="utf-8"))

        limits = dict(
            min_green=args.min_green,
            max_green=args.max_green,
            min_yellow=args.min_yellow,
            max_yellow=args.max_yellow,
            min_red=args.min_red,
            max_red=args.max_red,
            min_cycle=args.min_cycle,
            max_cycle=args.max_cycle,
        )

        compat_map = _compat_map_from_scenario_yaml(args.scenario_yaml) if args.scenario_yaml else None

        apply_plan_from_dict(
            cfg_path=args.cfg,
            plan_dict=plan,
            steps=args.steps,
            use_gui=args.gui,
            save_json_dir=args.save_json_dir,
            limits_override=limits,
            compat_map=compat_map,
        )
        return

    # --------- Fallback: tu comportamiento original (plan simple) ---------
    ensure_traci_on_path()
    import traci
    from tls_model import (
        TLSPhaseSpec,
        TLSPlanSpec,
        group_links_by_incoming_edge,
        validate_ranges,
        build_program_states,
    )
    from traci import trafficlight as tl

    net_path = parse_cfg(args.cfg)
    if not os.path.isabs(net_path):
        net_path = os.path.abspath(net_path)

    bin_name = "sumo-gui" if args.gui else "sumo"
    cmd = [bin_name, "-c", args.cfg, "--no-step-log", "true", "--duration-log.disable", "true"]
    print(">> SUMO:", " ".join(cmd))
    traci.start(cmd)

    try:
        tls_ids = traci.trafficlight.getIDList()
        if not tls_ids:
            print(">> No hay semáforos (TLS) en esta red.")
            return

        print(">> TLS encontrados:", list(tls_ids))

        # Inspección: agrupa links por edge entrante (=aproximación)
        tls_maps = {}
        for tid in tls_ids:
            links = traci.trafficlight.getControlledLinks(tid)
            mapping = group_links_by_incoming_edge(links)
            tls_maps[tid] = mapping
            approaches = list(dict.fromkeys(mapping.values()))
            print(f"   - {tid}: {len(mapping)} señales, aproximaciones={approaches}")

        if args.inspect_only:
            return

        # Construir un plan simple (mismas duraciones para todas las aproximaciones) y aplicarlo en cada TLS
        for tid in tls_ids:
            mapping = tls_maps[tid]
            approaches = []
            # mantener orden determinista por edge entrante
            for idx in sorted(mapping.keys()):
                ap = mapping[idx]
                if ap not in approaches:
                    approaches.append(ap)

            phases = [TLSPhaseSpec(ap, args.green, args.yellow, args.red) for ap in approaches]
            plan = TLSPlanSpec(tls_id=tid, phases=phases, offset_s=args.offset)

            # === NUEVO: sanear plan simple ===
            limits_dict = dict(
                min_green=args.min_green, max_green=args.max_green,
                min_yellow=args.min_yellow, max_yellow=args.max_yellow,
                min_red=args.min_red, max_red=args.max_red,
                min_cycle=args.min_cycle, max_cycle=args.max_cycle,
            )
            phases_sane, off_sane = _sanitize_plan_spec(plan.phases, plan.offset_s, limits=limits_dict, q=0.5)
            plan.phases = phases_sane
            plan.offset_s = off_sane
            # =================================

            # Validaciones de rangos y armado de estados
            validate_ranges(
                plan,
                min_green=args.min_green,
                max_green=args.max_green,
                min_yellow=args.min_yellow,
                max_yellow=args.max_yellow,
                min_red=args.min_red,
                max_red=args.max_red,
                min_cycle=args.min_cycle,
                max_cycle=args.max_cycle,
            )

            states = build_program_states(plan, mapping)  # [(state, dur), ...]

            # Convertir a objetos Phase/Logic de TraCI y aplicar
            phases_traci = [tl.Phase(dur, st) for (st, dur) in states]
            logic = tl.Logic(plan.program_id, 0, 0, phases_traci)  # (programID, type, currentPhaseIndex, phases)
            traci.trafficlight.setCompleteRedYellowGreenDefinition(tid, logic)
            traci.trafficlight.setProgram(tid, plan.program_id)

            # Aplicar offset: avanzar dentro del ciclo al punto deseado
            cycle = plan.cycle_s
            off = plan.offset_s % cycle if cycle > 0 else 0.0
            # Encontrar fase y tiempo restante
            acc = 0.0
            phase_index = 0
            remaining = phases_traci[0].duration
            for i, ph in enumerate(phases_traci):
                if acc + ph.duration > off:
                    phase_index = i
                    remaining = ph.duration - (off - acc)
                    break
                acc += ph.duration
            traci.trafficlight.setPhase(tid, phase_index)
            # Ajustar duración residual de la fase actual para respetar offset
            traci.trafficlight.setPhaseDuration(tid, remaining)
            print(
                f">> {tid}: aplicado plan '{plan.program_id}' con ciclo={cycle:.1f}s "
                f"offset={off:.1f}s (fase={phase_index}, restante={remaining:.1f}s)"
            )

        # Correr unos steps para ver el plan en acción
        for step in range(args.steps):
            traci.simulationStep()
            if step % 100 == 0:
                print("step=", step)

        print(">> OK: Planes TLS aplicados.")
    finally:
        traci.close(False)


if __name__ == "__main__":
    main()
