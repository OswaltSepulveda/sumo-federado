# template_follow_vehicle.py
# Step 1: Add modules
import os
import sys
import traceback

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
# Change this path if your sumocfg is elsewhere (use raw string r"...")
SUMOCFG = r"C:\Users\oswal\Desktop\ITLA\IA Distribuida\sumo-federado\arista 2/simulacion_arista2.sumocfg"

# find sumo binary
sumo_gui = os.path.join(SUMO_HOME, "bin", "sumo-gui.exe")
sumo_cli = os.path.join(SUMO_HOME, "bin", "sumo.exe")
if os.path.exists(sumo_gui):
    sumo_bin = sumo_gui
elif os.path.exists(sumo_cli):
    sumo_bin = sumo_cli
else:
    sys.exit("No sumo binary found in SUMO_HOME/bin. Check your installation.")

# build command (you can add --remote-port "8813" if you prefer connecting to a running SUMO)
Sumo_config = [
    sumo_bin,
    "-c", SUMOCFG,
    "--step-length", "0.05",
    "--lateral-resolution", "0.1"
]

# Step 5: Open connection between SUMO and Traci
try:
    print("Starting SUMO with command:", " ".join(f'"{c}"' if " " in c else c for c in Sumo_config))
    traci.start(Sumo_config)
except Exception:
    print("Failed to start SUMO via traci.start(). Traceback:")
    traceback.print_exc()
    sys.exit(1)

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

# Step 8: Simulation loop
try:
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        tracked, total_speed, samples = update_speed(tracked, total_speed, samples, flow_prefix="veh1")
finally:
    # Step 9: Close connection
    traci.close()
    print("TraCI closed.")

# Resultado final (evita división por cero)
if samples > 0:
    print(f"Average observed speed for tracked samples: {total_speed/samples:.3f} m/s over {samples} samples")
else:
    print("No speed samples were collected.")


    