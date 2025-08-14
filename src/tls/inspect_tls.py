# src/tls/inspect_tls.py
import argparse, os, sys, xml.etree.ElementTree as ET
from pathlib import Path

def parse_cfg(cfg_path: Path) -> Path:
    tree = ET.parse(cfg_path)
    root = tree.getroot()
    for inp in root.findall(".//input"):
        n = inp.find("net-file")
        if n is not None and "value" in n.attrib:
            net_file = n.attrib["value"]
            break
    else:
        raise RuntimeError("No <net-file> en cfg.sumocfg")
    return (cfg_path.parent / net_file).resolve() if not os.path.isabs(net_file) else Path(net_file)

def make_traci_cmd(cfg_path: Path, gui=False):
    import shutil
    exe = "sumo-gui" if gui else "sumo"
    if not shutil.which(exe):
        raise RuntimeError(f"No se encuentra {exe} en PATH")
    return [exe, "-c", str(cfg_path), "--no-step-log", "true", "--duration-log.disable", "true"]

def main():
    ap = argparse.ArgumentParser("Inspecciona TLS y aproximaciones (controlled links) con TraCI")
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--save-yaml-scaffold")
    args = ap.parse_args()

    try:
        import traci
    except Exception:
        print("[ERROR] No se puede importar TraCI (revisa SUMO_HOME / PYTHONPATH tools/)", file=sys.stderr)
        raise

    cfg = Path(args.cfg)
    net_path = parse_cfg(cfg)
    cmd = make_traci_cmd(cfg, gui=args.gui)
    traci.start(cmd)

    tls_ids = traci.trafficlight.getIDList()
    print(f"# TLS encontrados: {len(tls_ids)}  (net: {net_path})")
    report = {}
    for tls_id in tls_ids:
        links = traci.trafficlight.getControlledLinks(tls_id)  # -> lista de grupos; cada elem: [(inLane, outLane, viaLane), ...]
        pairs = []
        for group in links:
            for (inlane, outlane, vialane) in group:
                in_edge = inlane.split("_")[0]
                out_edge = outlane.split("_")[0]
                pairs.append((in_edge, out_edge))
        incoming = sorted({p[0] for p in pairs})
        outgoing = sorted({p[1] for p in pairs})

        print(f"\nTLS: {tls_id}")
        print("  incoming (aproximaciones):")
        for e in incoming: print(f"    - {e}")
        print("  outgoing:")
        for e in outgoing: print(f"    - {e}")

        report[tls_id] = {"incoming": incoming, "outgoing": outgoing, "pairs": pairs}

    traci.close()

    if args.save_yaml_scaffold:
        import yaml
        data = {
            "tls_defaults": {
                "green": 12, "yellow": 3, "red": 1, "offset": 0,
                "min_green": 5, "max_green": 60, "min_yellow": 2, "max_yellow": 5,
                "min_red": 0, "max_red": 10, "min_cycle": 20, "max_cycle": 240,
            },
            "tls": {},
        }
        for tid in report:
            data["tls"][tid] = {
                "offset": 0,
                "compatibility_groups": [[], []],
                "phases": [
                    {"active_approaches": [], "g": 12, "y": 3, "r": 1},
                    {"active_approaches": [], "g": 12, "y": 3, "r": 1},
                ],
            }
        outp = Path(args.save_yaml_scaffold)
        outp.parent.mkdir(parents=True, exist_ok=True)
        with open(outp, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        print(f"\n[OK] Scaffold YAML escrito en: {outp}")

if __name__ == "__main__":
    main()
