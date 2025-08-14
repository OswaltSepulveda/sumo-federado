# src/sim/traci_inject.py
import os, sys, argparse, xml.etree.ElementTree as ET
from typing import List
import random

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
    # Formato corto: <input net-file="..."/>
    for inp in root.findall("input"):
        nf = inp.get("net-file")
        if nf:
            return nf
        # Formato largo: <input><net-file value="..."/></input>
        for nf2 in inp.findall("net-file"):
            val = nf2.get("value")
            if val:
                return val
    # También, por si acaso, en la raíz
    nf = root.get("net-file")
    if nf:
        return nf
    raise RuntimeError("No se pudo hallar net-file en el .sumocfg")

def main():
    parser = argparse.ArgumentParser(
        description="Inyección de vehículos con ruta por nodos y planner GREEDY/BFS/UCS."
    )
    parser.add_argument("--cfg", required=True, help="Ruta a .sumocfg")
    parser.add_argument("--algo", choices=["bfs", "ucs", "greedy"], default="ucs")
    parser.add_argument("--metric", choices=["distance", "time"], default="distance",
                        help="Métrica de coste para UCS ('distance' o 'time')")
    parser.add_argument("--avoid-left", action="store_true",
                        help="Penaliza giros a la izquierda en UCS")
    parser.add_argument("--left-penalty-seconds", type=float, default=5.0,
                        help="Penalización por giro a la izquierda (segundos)")
    parser.add_argument("--nodes", action="append",
                        help="Lista de nodos separados por coma. Puede repetirse.")
    parser.add_argument("--auto-k", type=int, default=0,
                        help="Elige K nodos aleatorios de la red para demo")
    parser.add_argument("--veh-prefix", default="demo")
    parser.add_argument("--type-id", default="DEFAULT_VEHTYPE",
                        help="typeID existente o a crear (ej. DEFAULT_VEHTYPE, passenger)")
    parser.add_argument("--depart-gap", type=int, default=10,
                        help="Pasos entre vehículos si se inyectan varios")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--gui", action="store_true", help="Usar sumo-gui")
    args = parser.parse_args()

    ensure_traci_on_path()
    import traci
    from route_planner import RoutePlanner
    import sumolib

    net_path = parse_net_from_cfg(args.cfg)
    if not os.path.isabs(net_path):
        net_path = os.path.abspath(net_path)

    # Arranca SUMO
    sumo_bin = "sumo-gui" if args.gui else "sumo"
    cmd = [sumo_bin, "-c", args.cfg, "--no-step-log", "true", "--duration-log.disable", "true"]
    print(">> SUMO:", " ".join(cmd))
    traci.start(cmd)

    # Asegura que el type-id exista; si no, créalo copiando del DEFAULT_VEHTYPE
    vt_ids = set(traci.vehicletype.getIDList())
    if args.type_id not in vt_ids:
        base = "DEFAULT_VEHTYPE" if "DEFAULT_VEHTYPE" in vt_ids else (next(iter(vt_ids)) if vt_ids else None)
        if base:
            traci.vehicletype.copy(base, args.type_id)
            print(f">> Creado typeID '{args.type_id}' copiando de '{base}'")
        else:
            traci.vehicletype.add(args.type_id)
            print(f">> Creado typeID vacío '{args.type_id}'")

    try:
        # Construcción de listas de nodos
        if not args.nodes and args.auto_k < 2:
            raise SystemExit("Debes pasar --nodes N1,N2[,N3...] o --auto-k >= 2")
        node_lists: List[List[str]] = []
        if args.nodes:
            for s in args.nodes:
                node_lists.append([t.strip() for t in s.split(",") if t.strip()])
        else:
            net = sumolib.net.readNet(net_path)
            all_nodes = [n.getID() for n in net.getNodes()]
            chosen = random.sample(all_nodes, k=args.auto_k)
            node_lists.append(chosen)
            print(">> AUTO nodes:", chosen)

        planner = RoutePlanner(net_path)

        # Inyección de vehículos
        depart_time = 0
        for i, nodes in enumerate(node_lists):
            edges = planner.plan(
                nodes,
                algo=args.algo,
                metric=args.metric,
                avoid_left=args.avoid_left,
                left_penalty_s=args.left_penalty_seconds
            )
            rid = f"r_{args.veh_prefix}_{i}"
            vid = f"veh_{args.veh_prefix}_{i}"

            traci.route.add(rid, edges)
            traci.vehicle.add(vid, rid, typeID=args.type_id, depart=str(depart_time))
            traci.vehicle.setLaneChangeMode(vid, 1621)  # prudente
            print(f">> Injected {vid}: nodes={nodes} edges={len(edges)} depart={depart_time} type={args.type_id}")
            depart_time += args.depart_gap

        # Simula
        for step in range(args.steps):
            traci.simulationStep()
            if step % 50 == 0:
                print(f"step={step} veh_left={traci.simulation.getMinExpectedNumber()}")
        print(">> OK fin simulación.")
    finally:
        traci.close(False)

if __name__ == "__main__":
    main()
