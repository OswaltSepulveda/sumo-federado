# src/eval/aggregate_metrics.py
import argparse, os, csv, glob, statistics
from pathlib import Path

def load_arrivals(arr_csv):
    tt_steps = []
    with open(arr_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                tt = float(row.get("travel_time_s") or 0.0)
            except:
                tt = 0.0
            if tt > 0:
                tt_steps.append(tt)
    return tt_steps

def load_summary(summary_csv):
    last_step = 0
    waiting_sum = 0.0
    with open(summary_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            last_step = int(float(row["step"]))
            waiting_sum += float(row.get("waiting_time_sum", 0.0))
    return last_step, waiting_sum

def main():
    ap = argparse.ArgumentParser(description="Agrega KPIs de una corrida (csv_dir) o múltiples.")
    ap.add_argument("--csv-dirs", nargs="+", required=True, help="Una o más carpetas con *_arrivals.csv y *_summary_step.csv")
    ap.add_argument("--out-csv", required=True)
    args = ap.parse_args()

    rows = []
    for cdir in args.csv_dirs:
        cdir = Path(cdir)
        arr = glob.glob(str(cdir / "*_arrivals.csv"))
        summ = glob.glob(str(cdir / "*_summary_step.csv"))
        if not arr or not summ:
            print(f"WARNING: faltan archivos en {cdir}")
            continue
        arr_csv = arr[0]; summ_csv = summ[0]
        tt = load_arrivals(arr_csv)
        steps, waiting_total = load_summary(summ_csv)
        if tt:
            avg_tt = statistics.mean(tt)
            med_tt = statistics.median(tt)
            p95_tt = sorted(tt)[int(0.95*len(tt))-1]
        else:
            avg_tt = med_tt = p95_tt = 0.0
        rows.append({
            "csv_dir": str(cdir),
            "sim_steps": steps,
            "throughput_veh": len(tt),
            "avg_travel_time_s": round(avg_tt, 3),
            "median_travel_time_s": round(med_tt, 3),
            "p95_travel_time_s": round(p95_tt, 3),
            "total_waiting_time": round(waiting_total, 3),
            "avg_waiting_time_per_veh": round(waiting_total/len(tt), 3) if tt else 0.0
        })

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            "csv_dir","sim_steps","throughput_veh","avg_travel_time_s","median_travel_time_s","p95_travel_time_s","total_waiting_time","avg_waiting_time_per_veh"
        ])
        w.writeheader()
        for r in rows: w.writerow(r)
    print(">> KPIs agregados en:", args.out_csv)

if __name__ == "__main__":
    main()
