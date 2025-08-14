#!/usr/bin/env python
import os
import sys
import argparse
import time

def ensure_traci_on_path():
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        raise EnvironmentError("SUMO_HOME no está definido. Configura SUMO_HOME y PYTHONPATH.")
    tools = os.path.join(sumo_home, "tools")
    if tools not in sys.path:
        sys.path.append(tools)

def main():
    parser = argparse.ArgumentParser(description="Smoke test: TraCI abre un escenario y avanza N steps.")
    parser.add_argument("--cfg", required=True, help="Ruta al archivo .sumocfg")
    parser.add_argument("--steps", type=int, default=100, help="Cantidad de pasos a simular")
    parser.add_argument("--gui", action="store_true", help="Usar sumo-gui en lugar de sumo headless")
    args = parser.parse_args()

    ensure_traci_on_path()
    import traci
    import sumolib  # noqa

    # Escoge binario
    sumo_binary = "sumo-gui" if args.gui else "sumo"

    sumo_cmd = [sumo_binary, "-c", args.cfg, "--no-step-log", "true", "--duration-log.disable", "true"]
    print(">> Lanzando:", " ".join(sumo_cmd))
    traci.start(sumo_cmd)

    try:
        for step in range(args.steps):
            traci.simulationStep()
            if step % 10 == 0:
                print(f"step={step} veh={traci.simulation.getMinExpectedNumber()}")
        print(">> OK: simulación finalizada.")
    finally:
        traci.close(False)

if __name__ == "__main__":
    main()
