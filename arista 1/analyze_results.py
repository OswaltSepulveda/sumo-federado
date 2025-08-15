#!/usr/bin/env python3
import argparse
import glob
import os
import csv
from datetime import datetime
import statistics

def find_latest_per_tls(scenario, run_id=None):
    pattern = f"per_tls_{scenario}_*.csv"
    files = glob.glob(pattern)
    if run_id:
        target = f"per_tls_{scenario}_{run_id}.csv"
        return target if os.path.exists(target) else None
    if not files:
        return None
    # ordenar por fecha modificacion y devolver el último
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def find_resultados_for_run(scenario, run_id):
    f = f"resultados_eval_1_{scenario}.csv"
    if not os.path.exists(f):
        return None
    # buscar la fila correspondiente a run_id
    with open(f, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("run_id") == run_id:
                return row
    # si no encontró run_id, devolver la última fila
    last = None
    with open(f, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            last = row
    return last

def find_generations(scenario, run_id):
    fname = f"summary_{scenario}_{run_id}.csv"
    if os.path.exists(fname):
        with open(fname, newline="") as fh:
            reader = csv.DictReader(fh)
            gens = [int(row["generation"]) for row in reader]
            return max(gens) if gens else None
    return None

def analyze(scenario, run_id=None, rounds=None, k_phases_default=8):
    per_tls_file = find_latest_per_tls(scenario, run_id)
    if not per_tls_file:
        print("No se encontró archivo per_tls para ese escenario/run_id.")
        return

    # si run_id no fue dado, extraerlo del nombre del archivo encontrado
    if not run_id:
        basename = os.path.basename(per_tls_file)
        # formato per_tls_{scenario}_{run_id}.csv
        parts = basename.split("_")
        if len(parts) >= 3:
            run_id = parts[-1].replace(".csv", "")

    resultados_row = find_resultados_for_run(scenario, run_id)
    gens = rounds if rounds is not None else find_generations(scenario, run_id)
    gens = gens if gens is not None else 15  # fallback

    # leer per_tls file
    rows = []
    with open(per_tls_file, newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)

    # construir la tabla solicitada
    table = []
    for r in rows:
        tls = r.get("tls")
        avg_queue = float(r.get("avg_queue_tls", 0))
        avg_wait = float(r.get("avg_wait_tls", 0))
        vehicle_count = float(r.get("vehicle_count_tls", 0))
        flow_tls = float(r.get("flow_tls", 0))
        road_rage = avg_queue * 10  # misma fórmula del sistema

        # Tiempo de inferencia: usamos eval_time global (no por TLS)
        eval_time = float(resultados_row.get("eval_time", 0)) if resultados_row else None

        # Ancho de banda estimado (por TLS): 2 * R * K * 8 bytes (up + down)
        K = None
        # intentar inferir K (número de fases) mirando el genoma no está en este CSV; fallback:
        K = k_phases_default

        upstream_per_round_bytes = K * 8  # bytes (float64)
        total_tls_bytes = 2 * gens * upstream_per_round_bytes  # up+down * R

        table.append({
            "tls": tls,
            "Tiempo de tapón (avg_queue)": round(avg_queue, 3),
            "Road rage": round(road_rage, 3),
            "Flujo vehicular por segundo": round(flow_tls, 6),
            "Tiempo de inferencia (s) [global]": round(eval_time, 6) if eval_time is not None else None,
            "Ancho de banda estimado (bytes, total por TLS)": int(total_tls_bytes)
        })

    # guardar tabla como CSV y mostrar
    out_csv = f"table_{scenario}_{run_id}.csv"
    fieldnames = ["tls", "Tiempo de tapón (avg_queue)", "Road rage", "Flujo vehicular por segundo", "Tiempo de inferencia (s) [global]", "Ancho de banda estimado (bytes, total por TLS)"]
    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in table:
            writer.writerow(row)

    # Imprimir resumen por consola
    print(f"\nTabla generada -> {out_csv}\n(ESCENARIO {scenario}, run_id {run_id})\n")
    for row in table:
        print(f"Semáforo {row['tls']}: Tapón={row['Tiempo de tapón (avg_queue)']}, RoadRage={row['Road rage']}, Flow={row['Flujo vehicular por segundo']}, EvalTime={row['Tiempo de inferencia (s) [global]']}, BW_est={row['Ancho de banda estimado (bytes, total por TLS)']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, required=True, help="Nombre del escenario (ej. RUSH)")
    parser.add_argument("--run_id", type=str, default=None, help="run_id (opcional). Si no se da, se toma el más reciente")
    parser.add_argument("--rounds", type=int, default=None, help="Número de rondas/generaciones (opcional). Si no se da, se intenta leer summary file")
    parser.add_argument("--k", type=int, default=8, help="Número de fases (K) para estimación de ancho de banda (por TLS)")
    args = parser.parse_args()

    analyze(args.scenario, run_id=args.run_id, rounds=args.rounds, k_phases_default=args.k)
