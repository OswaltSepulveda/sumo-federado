# src/eval/run_baselines.py
import argparse, os, subprocess, sys, json, shutil
from pathlib import Path
from datetime import datetime

SCENARIOS = {
    "grid_3x3":  {"cfg": "sumo/scenarios/grid_3x3/cfg.sumocfg",  "steps": 1200},
    "arterial":  {"cfg": "sumo/scenarios/arterial/cfg.sumocfg",  "steps": 1200},
    "ring":      {"cfg": "sumo/scenarios/ring/cfg.sumocfg",      "steps": 1200},
    "downtown":  {"cfg": "sumo/scenarios/downtown/cfg.sumocfg",  "steps": 1500},
    "rushhour":  {"cfg": "sumo/scenarios/rushhour/cfg.sumocfg",  "steps": 1800},
}

def run(cmd):
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)

def main():
    ap = argparse.ArgumentParser(description="Ejecuta baselines TLS por escenario.")
    ap.add_argument("--scenario", choices=list(SCENARIOS.keys()) + ["all"], required=True)
    ap.add_argument("--plan", choices=["static_fallback","coordinated","both"], default="both")
    ap.add_argument("--yaml-dir", default="configs/scenarios", help="Carpeta YAML de escenarios")
    ap.add_argument("--results-root", default="experiments/baselines", help="Raíz de resultados")
    ap.add_argument("--print-every", type=int, default=50)
    ap.add_argument("--gui", action="store_true")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def run_one(sname, plan_name):
        cfg = SCENARIOS[sname]["cfg"]
        steps = SCENARIOS[sname]["steps"]
        outdir = Path(args.results_root) / sname / plan_name / ts
        csv_dir = outdir / "csv"
        json_dir = outdir / "plans"
        csv_dir.mkdir(parents=True, exist_ok=True)
        json_dir.mkdir(parents=True, exist_ok=True)

        # 1) Aplica plan (steps=0 para solo setear lógica TLS)
        if plan_name == "coordinated":
            yaml_path = Path(args.yaml_dir) / f"{sname}.yaml"
            cmd_apply = ["python", "src/tls/tls_apply.py", "--cfg", cfg,
                         "--plan-yaml", str(yaml_path),
                         "--steps", "0", "--save-json-dir", str(json_dir)]
        else:  # static_fallback
            # usa defaults del apply (una vía a la vez); también guardamos JSON
            cmd_apply = ["python", "src/tls/tls_apply.py", "--cfg", cfg,
                         "--steps", "0", "--save-json-dir", str(json_dir)]
        if args.gui: cmd_apply.append("--gui")
        run(cmd_apply)

        # 2) Corre métricas
        cmd_metrics = ["python", "src/sim/traci_metrics.py",
                       "--cfg", cfg, "--steps", str(steps),
                       "--print-every", str(args.print_every),
                       "--out-dir", str(csv_dir)]
        if args.gui: cmd_metrics.append("--gui")
        run(cmd_metrics)

        print(f">> OK baseline {sname}/{plan_name} guardado en: {outdir}")
        return outdir

    scenarios = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    plans = ["static_fallback","coordinated"] if args.plan == "both" else [args.plan]

    outputs = []
    for s in scenarios:
        for p in plans:
            outputs.append(str(run_one(s, p)))

    # opcional: imprimir lista para que un pipeline posterior agregue KPIs
    print("::OUTPUT_DIRS::")
    for o in outputs:
        print(o)

if __name__ == "__main__":
    main()
