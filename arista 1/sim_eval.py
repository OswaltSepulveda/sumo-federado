# sim_eval.py
import os
import csv
import time
import traci
import sumolib
from datetime import datetime
import traceback

# Módulo separado con evaluate_genome para evitar importaciones circulares.
# Esta versión captura logs de SUMO y maneja cierres inesperados, devolviendo un fitness muy bajo
# en caso de fallo para que el GA pueda continuar.

def evaluate_genome(genome, net_file, route_file, scenario, run_id, sumo_binary="sumo"):
    """
    Ejecuta SUMO con el genoma (configuración de fases) aplicado a todos los TLS.
    Retorna un fitness scalar (mayor es mejor).
    Escribe resultados en:
      - resultados_eval_1_{scenario}.csv (global)
      - per_tls_{scenario}_{run_id}.csv (por semáforo)
    En caso de que SUMO cierre la conexión, captura el log y devuelve un fitness muy bajo.
    """
    # Preparar comando SUMO con log-file para obtener diagnostico en caso de fallo
    logfile = f"sumo_{scenario}_{run_id}.log"
    sumoCmd = [
        sumo_binary,
        "-n", net_file,
        "-r", route_file,
        "--start",
        "--no-step-log",
        "--log-file", logfile
    ]

    start_eval = time.time()
    started = False

    try:
        # Intentar iniciar SUMO
        traci.start(sumoCmd)
        started = True

        tls_list = traci.trafficlight.getIDList()

        # Aplicar tiempos de fase del genoma a cada TLS (manipular la lista completa)
        for tls in tls_list:
            # Obtener lista de definiciones (puede devolver lista de lógicas)
            defs = traci.trafficlight.getCompleteRedYellowGreenDefinition(tls)
            if not defs:
                # Si no hay definiciones, saltar (no debería pasar)
                continue

            # Modificamos la primera definición (usualmente la principal)
            try:
                defs_mod = list(defs)
                tl_logic = defs_mod[0]
                for phase_index, phase in enumerate(tl_logic.phases):
                    dur = int(genome[phase_index % len(genome)])
                    if dur < 1:
                        dur = 1
                    phase.duration = dur
                traci.trafficlight.setCompleteRedYellowGreenDefinition(tls, defs_mod)
            except Exception as e:
                print(f"[WARN] No se pudo aplicar definiciones TLS para {tls}: {e}")

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
                    try:
                        queue += traci.lane.getLastStepHaltingNumber(lane)
                        wait += traci.lane.getWaitingTime(lane)
                        # recolectar veh IDs si disponible
                        try:
                            veh_ids = traci.lane.getLastStepVehicleIDs(lane)
                            for vid in veh_ids:
                                tls_metrics[tls]["veh_set"].add(vid)
                        except Exception:
                            pass
                    except Exception:
                        pass

                total_queue += queue
                total_wait += wait
                tls_metrics[tls]["queue"] += queue
                tls_metrics[tls]["wait"] += wait
                tls_metrics[tls]["steps"] += 1

        # Obtener stats de simulación ANTES de cerrar
        sim_time_ms = traci.simulation.getCurrentTime()  # ms
        total_veh = traci.simulation.getArrivedNumber()
        sim_time = sim_time_ms / 1000.0 if sim_time_ms is not None else (total_steps if total_steps > 0 else 1)

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

        # Guardar métricas por TLS
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

    except Exception as e:
        print("[ERROR] Excepción al ejecutar SUMO/TraCI:")
        traceback.print_exc()

        # Intentar leer el logfile para mostrar la última parte que ayude al diagnóstico
        try:
            if os.path.exists(logfile):
                print(f"\n--- Últimas líneas de {logfile} ---")
                with open(logfile, "r", encoding="utf-8", errors="ignore") as lf:
                    lines = lf.readlines()
                    tail = lines[-40:] if len(lines) > 40 else lines
                    for line in tail:
                        print(line.rstrip())
                print("--- fin del log ---\n")
        except Exception as e_log:
            print(f"[WARN] No se pudo leer log {logfile}: {e_log}")

        # Guardar una fila indicando fallo en resultados para que haya rastro
        try:
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
                    "fitness": -1e9,
                    "avg_travel": None,
                    "avg_wait": None,
                    "avg_queue": None,
                    "jam_penalty": None,
                    "flow": None,
                    "eval_time": time.time() - start_eval,
                    "sim_time_sec": None,
                    "total_veh": None
                })
        except Exception:
            pass

        return -1e9

    finally:
        try:
            if started:
                traci.close()
        except Exception:
            pass
