# eval_1.py
import argparse
from datetime import datetime
from ga_opt import run_ga_optimization

# Script de lanzamiento: solo coordina argumentos y llama al GA.
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pop", type=int, default=30, help="Población GA")
    parser.add_argument("--gen", type=int, default=15, help="Generaciones GA")
    parser.add_argument("--scenario", type=str, default="default", help="Nombre del escenario")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    net_file = "map.net.xml"
    route_file = "routes.rou.xml"

    run_ga_optimization(
        pop_size=args.pop,
        generations=args.gen,
        net_file=net_file,
        route_file=route_file,
        scenario=args.scenario,
        run_id=run_id
    )
