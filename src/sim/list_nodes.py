# src/sim/list_nodes.py
import argparse, os
import sumolib

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", required=True, help="Ruta al .net.xml")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    if not os.path.exists(args.net):
        raise FileNotFoundError(args.net)

    net = sumolib.net.readNet(args.net)
    nodes = [(n.getID(),) + n.getCoord() for n in net.getNodes()]
    print(f"# total nodes: {len(nodes)}")
    for i, (nid, x, y) in enumerate(nodes[: args.limit], 1):
        print(f"{i:4d}  {nid:20s}  x={x:9.2f}  y={y:9.2f}")
