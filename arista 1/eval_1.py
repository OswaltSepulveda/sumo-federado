# eval_1.py
# Step 1: Add modules
import os
import sys
import traceback
import numpy as np
import yaml
import csv
from datetime import datetime

# Step 2: Establish path to SUMO (SUMO_HOME) and tools
SUMO_HOME = os.environ.get("SUMO_HOME")
if not SUMO_HOME:
    sys.exit("Please declare environment variable 'SUMO_HOME'.")

tools = os.path.join(SUMO_HOME, "tools")
if os.path.isdir(tools):
    sys.path.append(tools)
else:
    print("WARNING: SUMO/tools not found.")

# Step 3: Import traci
try:
    import traci
except Exception:
    print("ERROR importing traci. Check SUMO_HOME.")
    raise

# Step 4: SUMO config
SUMOCFG = r"C:\Users\oswal\Desktop\ITLA\IA Distribuida\sumo-federado\arista 1\1_arista_simulation.sumocfg"
sumo_gui = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe")
sumo_cli = os.path.join(SUMO_HOME, "bin", "sumo.exe")
sumo_bin = sumo_gui if os.path.exists(sumo_gui) else sumo_cli
if not os.path.exists(sumo_bin):
    sys.exit("No SUMO binary found.")

Sumo_config = [
    sumo_bin,
    "-c", SUMOCFG,
    "--step-length", "0.05",
    "--lateral-resolution", "0.1"
]

# Step 5: Load config or defaults
try:
    with open("config/sim_config.yaml", "r") as f:
        SIMCONF = yaml.safe_load(f)
except FileNotFoundError:
    SIMCONF = {
        "sumo": {"warmup_steps": 100, "sim_steps": 1000, "step_length": 0.05},
        "fitness": {
            "weights": {"travel_time": 1.0, "waiting_time": 2.0, "queue_len": 1.5},
            "road_rage": {"jam_threshold": 10, "penalty_per_step": 5.0}
        },
        "traffic": {"traffic_lights": [], "phases_per_tls": 6}
    }

# Step 6: TraCI helpers
def start_sumo():
    try:
        traci.start(Sumo_config)
    except Exception:
        print("Failed to start SUMO.")
        traceback.print_exc()
        sys.exit(1)

def close_sumo():
    traci.close()

# Detect TLS & phases dynamically
def _ensure_traffic_lights_loaded():
    traffic_conf = SIMCONF.get("traffic", {})
    if traffic_conf.get("traffic_lights"):
        return
    tls_ids = []
    started_temp = False
    try:
        start_sumo()
        started_temp = True
        tls_ids = traci.trafficlight.getIDList()
        phases_map = {tls: len(traci.trafficlight.getAllProgramLogics(tls)[0].phases) for tls in tls_ids}
        SIMCONF["traffic"]["traffic_lights"] = tls_ids
        SIMCONF["traffic"]["phases_per_tls_map"] = phases_map
        if len(set(phases_map.values())) == 1:
            SIMCONF["traffic"]["phases_per_tls"] = list(phases_map.values())[0]
        else:
            SIMCONF["traffic"]["phases_per_tls"] = max(phases_map.values())
    finally:
        if started_temp:
            close_sumo()

# Step 7: Apply genome to TLS
def apply_genome_to_tls(genome: np.ndarray, tls_list):
    phases_per_tls = SIMCONF["traffic"]["phases_per_tls"]
    for i, tls_id in enumerate(tls_list):
        start = i * phases_per_tls
        for phase in range(phases_per_tls):
            traci.trafficlight.setPhaseDuration(tls_id, genome[start + phase])

# Step 8: Evaluate genome
def evaluate_genome(genome: np.ndarray, gen_num=None, ind_num=None) -> dict:
    start_sumo()
    tls_list = traci.trafficlight.getIDList()
    apply_genome_to_tls(genome, tls_list)

    warmup = SIMCONF["sumo"]["warmup_steps"]
    sim_steps = SIMCONF["sumo"]["sim_steps"]
    step_len = SIMCONF["sumo"]["step_length"]

    for _ in range(warmup):
        traci.simulationStep()

    total_travel = total_wait = total_queue = jam_penalty = 0.0
    vehicles_seen = set()

    for _ in range(sim_steps):
        traci.simulationStep()
        step_queue = sum(traci.edge.getLastStepHaltingNumber(e) for e in traci.edge.getIDList())
        step_wait = sum(traci.edge.getWaitingTime(e) for e in traci.edge.getIDList())
        total_queue += step_queue
        total_wait += step_wait
        if step_queue >= SIMCONF["fitness"]["road_rage"]["jam_threshold"]:
            jam_penalty += SIMCONF["fitness"]["road_rage"]["penalty_per_step"]
        for v in traci.vehicle.getIDList():
            vehicles_seen.add(v)
            total_travel += step_len

    close_sumo()

    steps = float(sim_steps)
    avg_queue = total_queue / steps
    avg_wait = total_wait / steps
    avg_travel = total_travel / max(1, len(vehicles_seen))
    w = SIMCONF["fitness"]["weights"]
    fitness = (
        w["travel_time"] * avg_travel
        + w["waiting_time"] * avg_wait
        + w["queue_len"] * avg_queue
        + jam_penalty
    )

    metrics = {
        "fitness": float(fitness),
        "avg_travel": float(avg_travel),
        "avg_wait": float(avg_wait),
        "avg_queue": float(avg_queue),
        "jam_penalty": float(jam_penalty),
        "generation": gen_num,
        "individual": ind_num
    }

    # Guardar resultados en CSV
    save_results(metrics)
    return metrics

# Guardado automático en CSV
def save_results(metrics: dict):
    filename = "resultados.csv"
    write_header = not os.path.exists(filename)
    with open(filename, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=metrics.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(metrics)

# Step 9: Optimize
def optimize_traffic_lights(pop_size=50, generations=100):
    from ga_opt import run_ga_opt
    _ensure_traffic_lights_loaded()
    tls_list = SIMCONF["traffic"]["traffic_lights"]
    best_genome, metrics = run_ga_opt(
        pop_size=pop_size,
        generations=generations,
        eval_fn=evaluate_genome,
        simconf=SIMCONF
    )
    phases_per_tls = SIMCONF["traffic"]["phases_per_tls"]
    tls_configs = {}
    for i, tls_id in enumerate(tls_list):
        start = i * phases_per_tls
        tls_configs[tls_id] = best_genome[start:start + phases_per_tls].tolist()
    return {"best_configs": tls_configs, "metrics": metrics}

# CLI
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("opt",), default="opt")
    parser.add_argument("--pop", type=int, default=20)
    parser.add_argument("--gen", type=int, default=10)
    args = parser.parse_args()

    result = optimize_traffic_lights(pop_size=args.pop, generations=args.gen)
    print("Configs óptimas:", result["best_configs"])
    print("Métricas:", result["metrics"])
