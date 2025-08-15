# sim_eval.py
import os
import csv
import time
import traci
import sumolib
from datetime import datetime

# Módulo separado con evaluate_genome para evitar importaciones circulares.
# Contiene la lógica de ejecución SUMO y extracción de métricas por TLS.

def evaluate_genome(genome, net_file, route_file, scenario, run_id):
    """
    Ejecuta SUMO con el genoma (configuración de fases) aplicado a todos los TLS.
    Retorna un fitness scalar (mayor es mejor).
    También escribe resultados en:
      - resultados_eval_1_{scenario}.csv (global)
      - per_tls_{scenario}_{run_id}.csv (por semáforo)
    """
    sumoBinary = "sumo"  # Cambia a "sumo-gui" si quieres ver la GUI
    sumoCmd = [sumoBinary, "-n", net_file, "-r", route_file, "--start"]

    start_eval = time.time()
    traci.start(sumoCmd)

    tls_list = traci.trafficlight.getIDList()

    # Aplicar tiempos de fase del genoma a cada TLS (compatibilidades TraCI)
    for tls in tls_list:
        program = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls)[0]
        for phase_index, phase in enumerate(program.phases):
            phase.duration = genome[phase_index % len(genome)]
        traci.trafficlight.setCompleteRedYellowGreenDefinition(tls, program)

    # Recolección por TLS (se guarda también set de vehículos para flujo por TLS)
    tls_metrics = {tls: {"queue": 0, "wait": 0, "steps": 0, "veh_set": set()} for tls in tls_list}
    total_steps = 0
    total_queue = 0
    total_wait = 0

    # Loop de simulación
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        total_steps += 1

        for tls in tls_list:
            controlled_lanes = traci.trafficlight.getControlledLanes(tls)
            queue = 0
            wait = 0
            for lane in controlled_lanes:
                # Estos métodos devuelven métricas por carril
                queue += traci.lane.getLastStepHaltingNumber(lane)
                wait += traci.lane.getWaitingTime(lane)
                # Intentar obtener IDs de vehículos en el carril para el conteo
                try:
                    veh_ids = traci.lane.getLastStepVehicleIDs(lane)
                    for vid in veh_ids:
                        tls_metrics[tls]["veh_set"].add(vid)
                except Exception:
                    # Si la versión de TraCI no soporta getLastStepVehicleIDs, lo ignoramos.
                    pass

            total_queue += queue
            total_wait += wait
            tls_metrics[tls]["queue"] += queue
            tls_metrics[tls]["wait"] += wait
            tls_metrics[tls]["steps"] += 1

    # Tomar stats de simulación ANTES de cerrar
    sim_time_ms = traci.simulation.getCurrentTime()  # en ms
    total_veh = traci.simulation.getArrivedNumber()
    sim_time = sim_time_ms / 1000.0 if sim_time_ms is not None else (total_steps if total_steps > 0 else 1)

    traci.close()

    # Cálculos globales
    avg_queue = total_queue / total_steps if total_steps > 0 else 0
    avg_wait = total_wait / total_steps if total_steps > 0 else 0
    jam_penalty = avg_queue * 10
    avg_travel = avg_wait / max(1, len(tls_list))
    fitness = 3000 - (avg_travel + avg_wait + jam_penalty)

    eval_time = time.time() - start_eval
    flow = total_veh / sim_time if sim_time > 0 else 0

    # Guardar métricas globales
    results_file = f"resultados_eval_1_{scenario}.csv"
    file_exists = os.path.exists(results_file)
    with open(results_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "scenario", "run_id", "fitness", "avg_travel", "avg_wait",
            "avg_queue", "jam_penalty", "flow", "eval_time", "sim_time_sec", "total_veh"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "scenario": scenario,
            "run_id": run_id,
            "fitness": fitness,
            "avg_travel": avg_travel,
            "avg_wait": avg_wait,
            "avg_queue": avg_queue,
            "jam_penalty": jam_penalty,
            "flow": flow,
            "eval_time": eval_time,
            "sim_time_sec": sim_time,
            "total_veh": total_veh
        })

    # Guardar métricas por TLS (incluye vehicle_count y flow_tls)
    tls_file = f"per_tls_{scenario}_{run_id}.csv"
    with open(tls_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "scenario", "run_id", "tls", "avg_queue_tls", "avg_wait_tls",
            "vehicle_count_tls", "flow_tls"
        ])
        if f.tell() == 0:
            writer.writeheader()
        for tls, m in tls_metrics.items():
            steps = m["steps"] if m["steps"] > 0 else 1
            vehicle_count = len(m["veh_set"])
            flow_tls = vehicle_count / sim_time if sim_time > 0 else 0
            writer.writerow({
                "scenario": scenario,
                "run_id": run_id,
                "tls": tls,
                "avg_queue_tls": m["queue"] / steps,
                "avg_wait_tls": m["wait"] / steps,
                "vehicle_count_tls": vehicle_count,
                "flow_tls": flow_tls
            })

    return fitness
