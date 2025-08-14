# src/sim/traci_metrics.py
import os, sys, csv, json, argparse, xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

def ensure_traci_on_path():
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        raise EnvironmentError("SUMO_HOME no está definido.")
    tools = os.path.join(sumo_home, "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)

def parse_net_from_cfg(cfg_path: str) -> str:
    tree = ET.parse(cfg_path)
    root = tree.getroot()
    for inp in root.findall("input"):
        nf = inp.get("net-file")
        if nf:
            return nf
        for nf2 in inp.findall("net-file"):
            val = nf2.get("value")
            if val:
                return val
    nf = root.get("net-file")
    if nf:
        return nf
    raise RuntimeError("No se pudo hallar net-file en el .sumocfg")

class NetIndex:
    """Índices útiles desde el .net.xml (nodos, aristas entrantes por nodo)."""
    def __init__(self, net_path: str):
        import sumolib
        self.net = sumolib.net.readNet(net_path)
        # aristas "driveable" (descarta internas)
        self.drive_edges = [e for e in self.net.getEdges() if e.getFunction() != "internal"]
        self.edge_ids = [e.getID() for e in self.drive_edges]
        # incoming edges por nodo destino
        self.node_in_edges: Dict[str, List[str]] = defaultdict(list)
        for e in self.drive_edges:
            nid = e.getToNode().getID()
            self.node_in_edges[nid].append(e.getID())

class MetricsWriter:
    """Gestión de carpetas y CSV/JSON."""
    def __init__(self, out_dir: str, tag: str):
        self.out_dir = out_dir
        self.tag = tag
        os.makedirs(out_dir, exist_ok=True)
        # archivos
        self.f_edges = open(os.path.join(out_dir, f"{tag}_edges_step.csv"), "w", newline="", encoding="utf-8")
        self.f_nodes = open(os.path.join(out_dir, f"{tag}_nodes_step.csv"), "w", newline="", encoding="utf-8")
        self.f_summary = open(os.path.join(out_dir, f"{tag}_summary_step.csv"), "w", newline="", encoding="utf-8")
        self.f_arrivals = open(os.path.join(out_dir, f"{tag}_arrivals.csv"), "w", newline="", encoding="utf-8")
        # writers
        self.w_edges = csv.writer(self.f_edges)
        self.w_nodes = csv.writer(self.f_nodes)
        self.w_summary = csv.writer(self.f_summary)
        self.w_arrivals = csv.writer(self.f_arrivals)
        # headers
        self.w_edges.writerow(["step","edge","vehCount","halting","meanSpeed","occupancy","flow_in_veh_s"])
        self.w_nodes.writerow(["step","node","flow_in_veh_s","halting_sum","vehCount_sum"])
        self.w_summary.writerow(["step","veh_in_net","waiting_time_sum","stops_sum"])
        self.w_arrivals.writerow(["vehID","depart_step","arrival_step","travel_time_steps","travel_time_s"])

    def write_edge_row(self, row): self.w_edges.writerow(row)
    def write_node_row(self, row): self.w_nodes.writerow(row)
    def write_summary_row(self, row): self.w_summary.writerow(row)
    def write_arrival_row(self, row): self.w_arrivals.writerow(row)

    def close(self):
        for f in [self.f_edges, self.f_nodes, self.f_summary, self.f_arrivals]:
            try: f.close()
            except: pass

def run_metrics(cfg: str, out_dir: str, steps: int, print_every: int, gui: bool):
    ensure_traci_on_path()
    import traci
    import sumolib

    # Parse & open
    net_path = parse_net_from_cfg(cfg)
    if not os.path.isabs(net_path):
        net_path = os.path.abspath(net_path)
    tag = os.path.splitext(os.path.basename(cfg))[0]  # ej. cfg.sumocfg -> cfg
    mw = MetricsWriter(out_dir, tag)
    net_index = NetIndex(net_path)

    # SUMO
    bin_name = "sumo-gui" if gui else "sumo"
    cmd = [bin_name, "-c", cfg, "--no-step-log", "true", "--duration-log.disable", "true"]
    print(">> SUMO:", " ".join(cmd))
    traci.start(cmd)
    dt_s = traci.simulation.getDeltaT() / 1000.0 if hasattr(traci.simulation, "getDeltaT") else 1.0

    # Estado por vehículo
    prev_edge: Dict[str, str] = {}
    seen: Dict[str, bool] = {}
    depart_step: Dict[str, int] = {}
    prev_stopped: Dict[str, bool] = {}
    stops_count: Dict[str, int] = {}

    try:
        for step in range(steps):
            traci.simulationStep()

            # Listas de ids
            v_ids = traci.vehicle.getIDList()
            e_ids = net_index.edge_ids  # evita internas

            # Flow por arista (entradas a edge en este step)
            flow_in = defaultdict(int)
            # Waiting time total y stops incremental
            waiting_sum = 0.0
            stops_sum_step = 0

            # Depart registry & flow transitions
            for vid in v_ids:
                if vid not in seen:
                    seen[vid] = True
                    depart_step[vid] = step
                    stops_count[vid] = 0
                cur_edge = traci.vehicle.getRoadID(vid)
                # cur_edge puede ser ":node_internal" al cruzar; ignoramos internas
                if cur_edge in e_ids:
                    # transición edge->edge
                    if prev_edge.get(vid) != cur_edge:
                        flow_in[cur_edge] += 1
                    prev_edge[vid] = cur_edge

                # waiting time y stops
                waiting_sum += traci.vehicle.getWaitingTime(vid)
                speed = traci.vehicle.getSpeed(vid)
                now_stopped = speed < 0.1
                if now_stopped and not prev_stopped.get(vid, False):
                    stops_count[vid] += 1
                    stops_sum_step += 1
                prev_stopped[vid] = now_stopped

            # Métricas por edge desde SUMO
            # (vehCount en edge, halting, meanSpeed, occupancy)
            edge_rows: List[Tuple] = []
            for eid in e_ids:
                vehCount = traci.edge.getLastStepVehicleNumber(eid)
                halting = traci.edge.getLastStepHaltingNumber(eid)
                meanSpeed = traci.edge.getLastStepMeanSpeed(eid)
                occupancy = traci.edge.getLastStepOccupancy(eid)
                fin = flow_in[eid] / dt_s if dt_s > 0 else flow_in[eid]
                edge_rows.append((eid, vehCount, halting, meanSpeed, occupancy, fin))
                mw.write_edge_row([step, eid, vehCount, halting, meanSpeed, occupancy, f"{fin:.6f}"])

            # Agregación por intersección (nodo): flujo entrante y halting/vehCount sum de sus aristas entrantes
            for node_id, in_edges in net_index.node_in_edges.items():
                fsum = sum(flow_in[e] for e in in_edges) / dt_s if dt_s > 0 else sum(flow_in[e] for e in in_edges)
                hsum = 0
                vhsum = 0
                for e in in_edges:
                    # obtener últimos valores escritos (ya los tenemos en edge_rows)
                    # para eficiencia, podrías cachear; aquí lo buscamos directo:
                    # (eid, vehCount, halting, meanSpeed, occupancy, fin)
                    # edge_rows es pequeño, el costo es bajo.
                    for row in edge_rows:
                        if row[0] == e:
                            vhsum += row[1]
                            hsum += row[2]
                            break
                mw.write_node_row([step, node_id, f"{fsum:.6f}", hsum, vhsum])

            # Summary del step
            veh_left = traci.simulation.getMinExpectedNumber()
            mw.write_summary_row([step, veh_left, f"{waiting_sum:.3f}", stops_sum_step])

            # Arrivals -> travel time
            arr = traci.simulation.getArrivedIDList()
            for vid in arr:
                dstep = depart_step.get(vid, None)
                if dstep is not None:
                    tsteps = step - dstep
                    tsecs = tsteps * dt_s
                    mw.write_arrival_row([vid, dstep, step, tsteps, f"{tsecs:.3f}"])

            # Vista tabular por "framerate"
            if print_every and step % print_every == 0:
                # Top-8 edges por halting en este step
                top = sorted(edge_rows, key=lambda r: r[2], reverse=True)[:8]
                print(f"\n[step {step}] veh_left={veh_left} waiting_sum={waiting_sum:.1f} stops+={stops_sum_step}")
                print("  edge              halting   veh  occ%   flow_in(veh/s)  meanSpeed(m/s)")
                for (eid, vnum, h, ms, occ, fin) in top:
                    print(f"  {eid:16s} {h:6d}  {vnum:4d}  {occ:4.1f}    {fin:8.3f}        {ms:6.2f}")

        print(">> Métricas completadas.")
    finally:
        mw.close()
        traci.close(False)

def main():
    ap = argparse.ArgumentParser(description="Extracción de métricas por step (edges/nodes/vehículos) con SUMO + TraCI.")
    ap.add_argument("--cfg", required=True, help="Ruta al archivo .sumocfg")
    ap.add_argument("--out-dir", default="experiments/results/csv", help="Carpeta de salida para CSV/JSON")
    ap.add_argument("--steps", type=int, default=1200, help="Pasos a simular")
    ap.add_argument("--print-every", type=int, default=50, help="Imprime tabla cada N steps (0 = silenciar)")
    ap.add_argument("--gui", action="store_true", help="Usar sumo-gui")
    args = ap.parse_args()
    run_metrics(args.cfg, args.out_dir, args.steps, args.print_every, args.gui)

if __name__ == "__main__":
    main()
