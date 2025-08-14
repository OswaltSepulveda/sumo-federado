import os, glob, subprocess, sys, json
from pathlib import Path

def run_metrics(cfg_path: str, steps: int, print_every: int = 100, gui: bool = False, out_dir: str = "experiments/runs/tmp"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    cmd = ["python", "src/sim/traci_metrics.py", "--cfg", cfg_path, "--steps", str(steps),
           "--out-dir", out_dir, "--print-every", str(print_every)]
    if gui: cmd.append("--gui")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError("metrics runner failed")
    # localizar CSVs
    arrivals = glob.glob(os.path.join(out_dir, "*_arrivals.csv"))
    summary  = glob.glob(os.path.join(out_dir, "*_summary_step.csv"))
    edges    = glob.glob(os.path.join(out_dir, "*_edges_step.csv"))
    nodes    = glob.glob(os.path.join(out_dir, "*_nodes_step.csv"))
    return {"arrivals": arrivals[0] if arrivals else None,
            "summary":  summary[0] if summary  else None,
            "edges":    edges[0]    if edges    else None,
            "nodes":    nodes[0]    if nodes    else None}

def simple_csv_parse(path, col):
    import csv
    vals=[]
    if not path: return vals
    with open(path, newline="", encoding="utf-8") as f:
        r=csv.DictReader(f)
        for row in r:
            try: vals.append(float(row.get(col, 0.0)))
            except: pass
    return vals

def compute_fitness_from_csv(csvs, weights):
    # costos negativos, beneficios positivos
    wait = sum(simple_csv_parse(csvs["summary"], "waiting_time_sum"))
    jam  = sum(simple_csv_parse(csvs["summary"], "jam_length_sum"))  # asegúrate de que la columna exista; si no, ajusta
    rage = sum(v*v for v in simple_csv_parse(csvs["edges"], "queue_len"))  # ejemplo: “road rage” como colas^2
    flow = len(simple_csv_parse(csvs["arrivals"], "travel_time_s"))        # throughput

    f = (weights["jam_time_w"] * jam +
         weights["wait_time_w"] * wait +
         weights["road_rage_w"] * rage +
         weights["flow_w"] * flow)
    return f
