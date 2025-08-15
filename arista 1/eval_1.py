# template_follow_vehicle.py
# Step 1: Add modules
import os
import sys
import traceback
import numpy as np  # Para genomas
import yaml  # Si usas config.yaml; ajusta si no
# from ga_opt import run_ga_opt   # <-- removido del tope para evitar import circular


# Step 2: Establish path to SUMO (SUMO_HOME) and tools
SUMO_HOME = os.environ.get("SUMO_HOME")
if not SUMO_HOME:
    sys.exit("Please declare environment variable 'SUMO_HOME' (path to SUMO installation).")

tools = os.path.join(SUMO_HOME, "tools")
if os.path.isdir(tools):
    sys.path.append(tools)  # needed so Python encuentre traci si viene con SUMO
else:
    print("WARNING: SUMO/tools not found in SUMO_HOME. If traci import fails, add it to PYTHONPATH.")

# Step 3: Add Traci
try:
    import traci
except Exception:
    print("ERROR importing traci. Check SUMO_HOME and that 'tools' is in sys.path.")
    raise

# Step 4: Define Sumo configuration (build full command to avoid connection issues)
# Change this path if your sumocfg is elsewhere (use raw string r“...”)
SUMOCFG = r"C:\Users\oswal\Desktop\ITLA\IA Distribuida\sumo-federado\arista 1\1_arista_simulation.sumocfg"

# find sumo binary
sumo_gui = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe")
sumo_cli = os.path.join(SUMO_HOME, "bin", "sumo.exe")
if os.path.exists(sumo_gui):
    sumo_bin = sumo_gui
elif os.path.exists(sumo_cli):
    sumo_bin = sumo_cli
else:
    sys.exit("No sumo binary found in SUMO_HOME/bin. Check your installation.")

# build command (you can add --remote-port “8813” if you prefer connecting to a running SUMO)
Sumo_config = [
    sumo_bin,
    "-c", SUMOCFG,
    "--step-length", "0.05",
    "--lateral-resolution", "0.1"
]

# Carga config si existe (ajusta path; si no usas yaml, quita esto)
try:
    with open("config/sim_config.yaml", "r") as f:
        SIMCONF = yaml.safe_load(f)
except FileNotFoundError:
    SIMCONF = {  # Defaults si no hay yaml
        "sumo": {"warmup_steps": 100, "sim_steps": 1000, "step_length": 0.05},
        "fitness": {
            "weights": {"travel_time": 1.0, "waiting_time": 2.0, "queue_len": 1.5},
            "road_rage": {"jam_threshold": 10, "penalty_per_step": 5.0}
        },
        "traffic": {"traffic_lights": traci.trafficlight.getIDList(), "phases_per_tls": 4}  # Obtén dinámicamente
    }

# Step 5: Open connection between SUMO and Traci
# (Lo movemos a funciones para reutilizar en evaluaciones)

def start_sumo():
    try:
        print("Starting SUMO with command:", " ".join(f'"{c}"' if " " in c else c for c in Sumo_config))
        traci.start(Sumo_config)
    except Exception:
        print("Failed to start SUMO via traci.start(). Traceback:")
        traceback.print_exc()
        sys.exit(1)

def close_sumo():
    traci.close()

# Step 6: Define Variables
vehicle_speed = 0.0
total_speed = 0.0
tracked = None
samples = 0

# Step 7: Define Functions
def update_speed(tracked_id, total_speed, samples, flow_prefix="veh1"):
    vehs = traci.vehicle.getIDList()
    # si no tenemos tracked, buscar el primer veh que empiece por el prefijo
    if not tracked_id and vehs:
        candidates = [v for v in vehs if v.startswith(flow_prefix)]
        if candidates:
            tracked_id = candidates[0]
            print(f"Siguiendo vehículo (prefijo='{flow_prefix}'): {tracked_id}")

    # si hay tracked y aún está en la simulación, leer su velocidad y acumular
    if tracked_id and tracked_id in vehs:
        try:
            vs = traci.vehicle.getSpeed(tracked_id)
            total_speed += vs
            samples += 1
            print(f"Vehicle {tracked_id} → speed = {vs:.3f} m/s (acum={samples})")
        except Exception as e:
            print("Error leyendo velocidad:", e)
    else:
        # opcional: cuando tracked desaparece, lo reseteamos para buscar otro
        if tracked_id and tracked_id not in vehs:
            print(f"El vehículo {tracked_id} ya no está en la simulación.")
            tracked_id = None

    return tracked_id, total_speed, samples 

def apply_genome_to_tls(genome: np.ndarray, tls_list):
    """
    Aplica el genoma a los semáforos. Asume genoma = [dur_fase1_tls1, dur_fase2_tls1, ..., dur_fase1_tlsN, ...]
    Ajusta según tu encoding (e.g., fases por tls).
    """
    phases_per_tls = 4  # Ajusta: # de fases por semáforo
    for i, tls_id in enumerate(tls_list):
        start = i * phases_per_tls
        for phase in range(phases_per_tls):
            duration = genome[start + phase]
            traci.trafficlight.setPhaseDuration(tls_id, phase, duration)

def evaluate_genome(genome: np.ndarray, realtime=False) -> dict:
    """
    Evalúa un genoma corriendo la simulación y calculando métricas.
    Similar a lo que te propuse antes.
    """
    start_sumo()
    tls_list = traci.trafficlight.getIDList()  # Obtén dinámicamente
    apply_genome_to_tls(genome, tls_list)

    warmup = SIMCONF["sumo"]["warmup_steps"]
    sim_steps = SIMCONF["sumo"]["sim_steps"]
    step_len = SIMCONF["sumo"]["step_length"]

    # Warmup sin métricas
    for _ in range(warmup):
        traci.simulationStep()

    total_travel = 0.0
    total_wait = 0.0
    total_queue = 0.0
    jam_penalty = 0.0
    vehicles_seen = set()

    for step in range(sim_steps):
        traci.simulationStep()

        edges = traci.edge.getIDList()
        step_queue = 0
        step_wait = 0

        for e in edges:
            step_queue += traci.edge.getLastStepHaltingNumber(e)
            step_wait += traci.edge.getWaitingTime(e)

        total_queue += step_queue
        total_wait += step_wait

        if step_queue >= SIMCONF["fitness"]["road_rage"]["jam_threshold"]:
            jam_penalty += SIMCONF["fitness"]["road_rage"]["penalty_per_step"]

        for v in traci.vehicle.getIDList():
            vehicles_seen.add(v)
            total_travel += step_len

        if realtime:
            avg_queue = total_queue / (step + 1)
            avg_wait = total_wait / (step + 1)
            avg_travel = total_travel / max(1, len(vehicles_seen))
            w = SIMCONF["fitness"]["weights"]
            fitness_now = (
                w["travel_time"] * avg_travel
                + w["waiting_time"] * avg_wait
                + w["queue_len"] * avg_queue
                + jam_penalty
            )
            print(
                f"[Paso {step+1}/{sim_steps}] "
                f"Travel={avg_travel:.2f}  Wait={avg_wait:.2f}  "
                f"Queue={avg_queue:.2f}  JamPenalty={jam_penalty:.2f}  "
                f"Fitness={fitness_now:.2f}"
            )

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

    return {
        "fitness": float(fitness),
        "avg_travel": float(avg_travel),
        "avg_wait": float(avg_wait),
        "avg_queue": float(avg_queue),
        "jam_penalty": float(jam_penalty),
    }

def optimize_traffic_lights(pop_size=50, generations=100):
    """
    Función para optimizar configuraciones de semáforos usando GA estándar.
    Retorna configs idóneas por semáforo.
    """
    # Importación local para evitar import circular
    from ga_opt import run_ga_opt

    tls_list = traci.trafficlight.getIDList()  # Obtén una vez (asumiendo simulación no iniciada)
    # pasamos evaluate_genome y SIMCONF al GA
    best_genome, metrics = run_ga_opt(pop_size=pop_size, generations=generations,
                                      eval_fn=evaluate_genome, simconf=SIMCONF)

    # Desglosar genoma por semáforo
    phases_per_tls = SIMCONF.get("traffic", {}).get("phases_per_tls", 4)  # Ajusta
    tls_configs = {}
    for i, tls_id in enumerate(tls_list):
        start = i * phases_per_tls
        end = start + phases_per_tls
        # aseguramos que best_genome sea indexable (si es numpy array o lista)
        tls_configs[tls_id] = best_genome[start:end].tolist() if hasattr(best_genome, "tolist") else list(best_genome[start:end])
    
    return {
        "best_configs": tls_configs,
        "metrics": metrics
    }

# Step 8: Simulation loop 
# Para correr simulación simple:
if __name__ == "__main__":
    start_sumo()
    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            tracked, total_speed, samples = update_speed(tracked, total_speed, samples, flow_prefix="veh1")
    finally:
        # Step 9: Close connection
        close_sumo()
        print("TraCI closed.")

    # Resultado final (evita división por cero)
    if samples > 0:
        print(f"Average observed speed for tracked samples: {total_speed/samples:.3f} m/s over {samples} samples")
    else:
        print("No speed samples were collected.")

# Para correr optimización (agrega esto al final o en un main)
# result = optimize_traffic_lights(pop_size=50, generations=100)
# print("Configs óptimas:", result["best_configs"])
# print("Métricas:", result["metrics"])
