# src/vis/plot_queues_flow.py
# Genera figuras (matplotlib) de colas (halting) por arista y flujo (veh/s) por intersección.
# - Lee *_edges_step.csv y *_nodes_step.csv producidos por traci_metrics.py
# - Guarda PNGs en experiments/results/figs/
#
# Uso:
#   python src/vis/plot_queues_flow.py --csv-dir experiments/results/csv --topk 6 --label grid_3x3
#   (si hay varios *_edges_step.csv en la carpeta, toma el más reciente)

import os, sys, argparse, glob, csv
from collections import defaultdict
import math

# Matplotlib (sin seaborn, sin estilos ni colores específicos)
import matplotlib.pyplot as plt

def _latest_csv(pattern: str) -> str:
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos que cumplan: {pattern}")
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]

def _read_edges_csv(path: str):
    # Devuelve: steps (ordenados) y dict edge -> lista según steps (halting, flow_in_veh_s)
    steps_set = set()
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                step = int(float(row["step"]))
            except Exception:
                step = int(row["step"])
            eid = row["edge"]
            halting = float(row["halting"])
            flow = float(row.get("flow_in_veh_s", 0.0))
            rows.append((step, eid, halting, flow))
            steps_set.add(step)

    steps = sorted(list(steps_set))
    # inicializa series
    halting_ts = defaultdict(lambda: [0.0]*len(steps))
    flow_ts = defaultdict(lambda: [0.0]*len(steps))
    idx_of_step = {s:i for i,s in enumerate(steps)}

    for step, eid, h, fin in rows:
        i = idx_of_step[step]
        halting_ts[eid][i] = h
        flow_ts[eid][i] = fin

    return steps, halting_ts, flow_ts

def _read_nodes_csv(path: str):
    # Devuelve: steps y dict node -> flow_ts
    steps_set = set()
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                step = int(float(row["step"]))
            except Exception:
                step = int(row["step"])
            nid = row["node"]
            fin = float(row.get("flow_in_veh_s", 0.0))
            rows.append((step, nid, fin))
            steps_set.add(step)

    steps = sorted(list(steps_set))
    flow_ts = defaultdict(lambda: [0.0]*len(steps))
    idx_of_step = {s:i for i,s in enumerate(steps)}
    for step, nid, fin in rows:
        flow_ts[nid][idx_of_step[step]] = fin
    return steps, flow_ts

def _topk_by_sum(series_dict, k):
    # series_dict: id -> list[float]; retorna ids con mayor suma
    scored = []
    for _id, arr in series_dict.items():
        scored.append((_id, sum(arr)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [i for i,_ in scored[:k]]

def main():
    ap = argparse.ArgumentParser(description="Plots de colas (halting) y flujo (veh/s) desde CSVs de métricas.")
    ap.add_argument("--csv-dir", required=True, help="Carpeta con *_edges_step.csv y *_nodes_step.csv")
    ap.add_argument("--topk", type=int, default=6, help="Top-K series a graficar")
    ap.add_argument("--label", default=None, help="Prefijo/título para los PNG (ej. grid_3x3). Si no, infiere del CSV")
    ap.add_argument("--out-dir", default="experiments/results/figs", help="Carpeta de salida para las figuras")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Localiza CSVs (toma los más recientes si hay varios)
    edges_csv = _latest_csv(os.path.join(args.csv_dir, "*_edges_step.csv"))
    nodes_csv = _latest_csv(os.path.join(args.csv_dir, "*_nodes_step.csv"))

    # Etiqueta de salida
    if args.label:
        tag = args.label
    else:
        # intenta inferir de nombre de carpeta padre o nombre de archivo
        tag = os.path.basename(os.path.dirname(edges_csv)) or "scenario"

    # --- Edges: colas (halting) top-K ---
    steps, halting_ts, _flow_ts_edges = _read_edges_csv(edges_csv)
    top_edges = _topk_by_sum(halting_ts, args.topk)

    plt.figure()
    for eid in top_edges:
        plt.plot(steps, halting_ts[eid], label=eid)
    plt.xlabel("step")
    plt.ylabel("vehículos detenidos (halting)")
    plt.title(f"Top-{args.topk} aristas por colas — {tag}")
    plt.legend(loc="best")
    out1 = os.path.join(args.out_dir, f"{tag}_edges_top{args.topk}_halting.png")
    plt.tight_layout()
    plt.savefig(out1, dpi=150)
    plt.close()

    # --- Nodos: flujo entrante (veh/s) top-K ---
    steps2, flow_ts_nodes = _read_nodes_csv(nodes_csv)
    top_nodes = _topk_by_sum(flow_ts_nodes, args.topk)

    plt.figure()
    for nid in top_nodes:
        plt.plot(steps2, flow_ts_nodes[nid], label=nid)
    plt.xlabel("step")
    plt.ylabel("flujo entrante (veh/s)")
    plt.title(f"Top-{args.topk} intersecciones por flujo — {tag}")
    plt.legend(loc="best")
    out2 = os.path.join(args.out_dir, f"{tag}_nodes_top{args.topk}_flow.png")
    plt.tight_layout()
    plt.savefig(out2, dpi=150)
    plt.close()

    print(">> Figuras guardadas:")
    print("   ", out1)
    print("   ", out2)

if __name__ == "__main__":
    main()
