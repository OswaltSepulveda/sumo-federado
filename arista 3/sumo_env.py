import os
import sys
import time
import math
import random
import numpy as np
import pandas as pd

# Asegura SUMO_HOME
if "SUMO_HOME" not in os.environ:
    # ajusta si tienes SUMO en otra ruta
    pass

from sumolib import checkBinary
import traci

# ------------------------------
# CONFIGURA TU ESCENARIO
# ------------------------------
SUMO_CFG = "3_arista_simulation.sumocfg"   # relativo a este script
USE_ADDITIONAL = False                     # True si quieres cargar semaforo_arista3.xml
ADDITIONAL = "semaforo_arista3.xml"

TLS_IDS = ["J3", "J11", "J13"]
# límites razonables
YELLOW_FIXED = 4            # s
GREEN_MIN, GREEN_MAX = 5, 70
CYCLE_MIN, CYCLE_MAX = 20, 150
SIM_STEPS = 3600            # 1 hora sim (ajusta)
STEP_LENGTH = 1.0           # s (coherente con tu sumocfg si lo cambias)
WARMUP = 60                 # s de warmup opcional

# pesos fitness
ALPHA, BETA, GAMMA, DELTA = 1.0, 0.8, 0.2, 0.5

def _bounded(x, lo, hi):
    return max(lo, min(hi, x))

class SumoEnv:
    """
    Aplica (green_NS, green_EW, offset) para cada TLS en TLS_IDS,
    simula y devuelve métricas agregadas + fitness.
    Cromosoma = [ (gNS, gEW, offset)_J3, (gNS,gEW,offset)_J11, (gNS,gEW,offset)_J13 ]
    """
    def __init__(self, gui=False, seed=None):
        self.gui = gui
        self.rnd = np.random.RandomState(seed if seed is not None else 42)

    def _build_cmd(self):
        sumoBinary = checkBinary("sumo-gui" if self.gui else "sumo")
        cmd = [sumoBinary, "-c", SUMO_CFG]
        if USE_ADDITIONAL and os.path.exists(ADDITIONAL):
            cmd += ["--additional-files", ADDITIONAL]
        # speeds & reproducibilidad opcionales
        # cmd += ["--seed", "123"]
        return cmd

    def _apply_tls(self, tls_id, green_NS, green_EW, offset):
        """
        Suponemos programa con dos fases de verde (NS y EW) separadas por amarillos.
        Reescribimos las duraciones manteniendo orden de fases existente.
        """
        prog_id = traci.trafficlight.getProgram(tls_id)
        nPh = traci.trafficlight.getPhaseNumber(tls_id)
        # Para robustez: detecta qué fases son "G" en NS/EW según el state.
        # Aquí asumimos patrón 4 fases: [NS-G, NS-Y, EW-G, EW-Y].
        # Si tu net usa más, amplía el mapeo.
        phases = [traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0].phases[i]
                  for i in range(nPh)]

        # Reasigna duraciones
        # Busca indices por contenido de 'state'
        def find_phase_idx(pred):
            for i, ph in enumerate(phases):
                if pred(ph.state):
                    return i
            return None

        # Heurística: NS tiene más 'G' en posiciones verticales (usa 'G' donde correspondan tus lanes).
        # Si tu patrón exacto difiere, reemplaza por indices fijos (ej. 0,1,2,3).
        idx_ns_g = find_phase_idx(lambda s: "G" in s and s.count("G") >= s.count("g"))
        idx_ew_g = find_phase_idx(lambda s: "G" in s and s != phases[idx_ns_g].state)
        # Amarillos: cualquiera con 'y' o 'Y'
        idx_ns_y = find_phase_idx(lambda s: "y" in s or "Y" in s)
        # busca otro amarillo distinto
        idx_ew_y = None
        for i, ph in enumerate(phases):
            if i != idx_ns_y and ("y" in ph.state or "Y" in ph.state):
                idx_ew_y = i
                break

        # Duraciones con límites
        gNS = int(_bounded(green_NS, GREEN_MIN, GREEN_MAX))
        gEW = int(_bounded(green_EW, GREEN_MIN, GREEN_MAX))
        y = int(YELLOW_FIXED)
        cycle = gNS + y + gEW + y
        if cycle < CYCLE_MIN:
            extra = CYCLE_MIN - cycle
            gNS += extra // 2
            gEW += extra - extra // 2
            cycle = gNS + y + gEW + y
        elif cycle > CYCLE_MAX:
            # recorta proporcional
            factor = (CYCLE_MAX - 2*y) / float(gNS + gEW)
            gNS = max(GREEN_MIN, int(gNS * factor))
            gEW = max(GREEN_MIN, int(gEW * factor))
            cycle = gNS + y + gEW + y

        # Aplica nuevos tiempos en el orden detectado
        def set_phase_duration(idx, dur):
            # crea una Phase nueva manteniendo state & next, cambiando dur
            ph = phases[idx]
            new_ph = traci.trafficlight.Phase(dur, ph.state, minDur=dur, maxDur=dur)
            phases[idx] = new_ph

        set_phase_duration(idx_ns_g, gNS)
        set_phase_duration(idx_ns_y, y)
        set_phase_duration(idx_ew_g, gEW)
        set_phase_duration(idx_ew_y, y)

        # Crea nueva definición
        logic = traci.trafficlight.Logic(programID=prog_id, type=0, currentPhaseIndex=0, phases=phases)
        traci.trafficlight.setCompleteRedYellowGreenDefinition(tls_id, logic)

        # Offset: desplaza fase inicial avanzando tiempo 'offset' a punta de steps rápidos
        if offset and offset > 0:
            ofs = int(_bounded(offset, 0, cycle - 1))
            # “quemamos” ofs segundos avanzando el semáforo
            # (sin avanzar la simulación global demasiado: hacemos múltiples setPhaseDuration decrecientes)
            # Alternativa simple: llamamos N veces a simulationStep antes del warmup.
            traci.trafficlight.setPhase(tls_id, 0)  # inicio consistente
            # guardamos duraciones actuales
            # (offset robusto: adelanta la simulación antes del WARMUP)
            self._offset_to_apply += ofs

    def evaluate(self, chromosome, run_id="run-0"):
        """
        chromosome: [gNS_J3, gEW_J3, off_J3,  gNS_J11, gEW_J11, off_J11,  gNS_J13, gEW_J13, off_J13]
        return: dict(metrics..., fitness)
        """
        cmd = self._build_cmd()
        traci.start(cmd)
        self._offset_to_apply = 0

        # Aplica a cada TLS
        for k, tls in enumerate(TLS_IDS):
            gNS, gEW, off = chromosome[3*k : 3*k+3]
            self._apply_tls(tls, gNS, gEW, off)

        # Warmup + offset “global”
        steps_to_burn = int(WARMUP + self._offset_to_apply)
        for _ in range(steps_to_burn):
            traci.simulationStep()

        # Métricas
        total_wait = 0.0
        total_queue = 0.0
        total_tt = 0.0
        throughput = 0
        steps = 0

        # Opcional: registra por edge para EDA
        per_step = []

        # Edges a medir: todos o un subconjunto
        edges = traci.edge.getIDList()

        while traci.simulation.getMinExpectedNumber() > 0 and steps < SIM_STEPS:
            traci.simulationStep()
            steps += 1

            # Waiting & queue
            wait_edges = []
            queue_edges = []
            for e in edges:
                # vehículos en edge
                vnum = traci.edge.getLastStepVehicleNumber(e)
                # cola aprox: vehículos con v<0.1
                queue_len = traci.edge.getLastStepHaltingNumber(e)
                # tiempo de espera total de los vehiculos del edge
                # (aprox con waitingTime acumulado de cada vehículo del edge)
                vehs = traci.edge.getLastStepVehicleIDs(e)
                w_e = sum(traci.vehicle.getWaitingTime(v) for v in vehs)
                # travel time estimado con length / mean speed
                mean_speed = traci.edge.getLastStepMeanSpeed(e) or 1e-3
                length = traci.lane.getLength(traci.edge.getLaneIDList(e)[0]) if traci.edge.getLaneNumber(e) > 0 else 1.0
                tt_e = length / mean_speed

                wait_edges.append(w_e)
                queue_edges.append(queue_len)
                total_tt += tt_e

            total_wait += np.sum(wait_edges)
            total_queue += np.sum(queue_edges)

            # throughput: vehículos que llegan a edges "salida"
            # heurística: cuenta vehículos que ya no están y finalizaron
            throughput = traci.simulation.getArrivedNumber()

            per_step.append({
                "step": steps,
                "wait": float(np.sum(wait_edges)),
                "queue": float(np.sum(queue_edges)),
                "throughput": throughput
            })

        traci.close(False)

        # Agregados
        avg_wait = total_wait / max(steps, 1)
        avg_queue = total_queue / max(steps, 1)
        avg_tt = total_tt / max(steps, 1)

        # fitness (menor es mejor)
        fitness = ALPHA*avg_wait + BETA*avg_queue + GAMMA*avg_tt - DELTA*throughput

        # Guarda CSV por corrida
        df = pd.DataFrame(per_step)
        os.makedirs("results", exist_ok=True)
        df.to_csv(f"results/{run_id}_timeseries.csv", index=False)

        return {
            "fitness": fitness,
            "avg_wait": avg_wait,
            "avg_queue": avg_queue,
            "avg_travel_time": avg_tt,
            "throughput": throughput,
            "steps": steps
        }
