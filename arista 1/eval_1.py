# eval_1.py
import argparse
from datetime import datetime
from ga_opt import run_ga_optimization

# Script de lanzamiento: solo orquesta la corrida del GA.
# NUEVO: Ahora acepta argumentos --net, --route y --gui para controlar SUMO.

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pop", type=int, default=30, help="Población GA")
    parser.add_argument("--gen", type=int, default=15, help="Generaciones GA")
    parser.add_argument("--scenario", type=str, default="default", help="Nombre del escenario")
    parser.add_argument("--net", type=str, default=r"C:\Users\luisc\Downloads\aristas\sumo-federado\arista 1\1_arista_simulation.net.xml", help="Archivo .net.xml de la red (NUEVO)")
    parser.add_argument("--route", type=str, default=r"C:\Users\luisc\Downloads\aristas\sumo-federado\arista 1\1_arista_simulation.rou.xml", help="Archivo .rou.xml de rutas (NUEVO)")
    parser.add_argument("--gui", action="store_true", help="Usar sumo-gui en lugar de sumo (NUEVO)")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")

    # Elegir binario segun flag --gui
    sumo_binary = "sumo-gui" if args.gui else "sumo"  # NUEVO: permite visualizar la simulación

    run_ga_optimization(
        pop_size=args.pop,
        generations=args.gen,
        net_file=args.net,
        route_file=args.route,
        scenario=args.scenario,
        run_id=run_id,
        sumo_binary=sumo_binary  # NUEVO: propagar al GA
    )
