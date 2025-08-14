import argparse, json, yaml, os
from pathlib import Path
from src.ga.optimizer import run_ga
from src.ga.encoding import TLSBounds

def load_yaml(p): 
    with open(p, "r", encoding="utf-8") as f: return yaml.safe_load(f)

def build_bounds_map_from_scenario_yaml(yaml_cfg):
    d = yaml_cfg.get("tls_defaults", {})
    b = TLSBounds(
        min_green=d.get("min_green",5), max_green=d.get("max_green",60),
        min_yellow=d.get("min_yellow",2), max_yellow=d.get("max_yellow",5),
        min_red=d.get("min_red",0), max_red=d.get("max_red",10),
        min_cycle=d.get("min_cycle",20), max_cycle=d.get("max_cycle",240),
    )
    # todos los tls comparten los mismos bounds por defecto
    return {"__default__": b}

def scenario_to_blueprint(yaml_cfg):
    # crea rangos de inicialización a partir de defaults (simple; puedes refinar por TLS)
    d = yaml_cfg.get("tls_defaults", {})
    tls = {}
    # si tienes lista explícita en yaml_cfg["tls"], la usamos; si no, el runner
    # puede inferir los TLS de la red y crear un blueprint homogéneo.
    for tid, spec in (yaml_cfg.get("tls") or {}).items():
        phases = spec.get("phases", [])
        phase_specs = []
        for ph in phases:
            phase_specs.append({
                "approaches": ph["active_approaches"],
                "g": (max(5, d.get("min_green",5)), min(20, d.get("max_green",60))),
                "y": (max(2, d.get("min_yellow",2)), min(4, d.get("max_yellow",5))),
                "r": (max(0, d.get("min_red",0)), min(5, d.get("max_red",10))),
            })
        tls[tid] = {"offset_range": (0, 30), "phases": phase_specs}
    return tls

def build_compat_map(yaml_cfg):
    comp = {}
    for tid, spec in (yaml_cfg.get("tls") or {}).items():
        if "compatibility_groups" in spec:
            comp[tid] = spec["compatibility_groups"]
    return comp

def main():
    ap = argparse.ArgumentParser(description="Optimiza planes TLS con Algoritmo Genético")
    ap.add_argument("--cfg", required=True, help="sumo .sumocfg")
    ap.add_argument("--scenario-yaml", required=True, help="configs/scenarios/<escenario>.yaml")
    ap.add_argument("--ga-yaml", default="configs/ga_default.yaml")
    ap.add_argument("--results-dir", default="experiments/runs/ga")
    args = ap.parse_args()

    scy = load_yaml(args.scenario_yaml)
    gay = load_yaml(args.ga_yaml)

    bounds_map = build_bounds_map_from_scenario_yaml(scy)
    compat_map = build_compat_map(scy)
    tls_blueprint = scenario_to_blueprint(scy)

    best = run_ga(
        tls_blueprint=tls_blueprint,
        cfg_path=args.cfg,
        ga_cfg=gay,
        bounds_map=bounds_map,
        compat_map=compat_map,
        results_dir=args.results_dir,
        seed=gay.get("seed", 42),
        scenario_yaml_path=args.scenario_yaml, 
    )
    # guarda mejor individuo como JSON plan
    outp = Path(args.results_dir) / "best_plan.json"
    plan = {"tls": {}}
    for tid, tls in best.genome.items():
        plan["tls"][tid] = {
            "offset": tls.offset,
            "phases": [{"active_approaches": p.active_approaches, "g": p.g, "y": p.y, "r": p.r} for p in tls.phases]
        }
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    print(">> BEST PLAN saved at:", outp)

if __name__ == "__main__":
    main()
