# src/sim/route_planner.py
import math
import heapq
from typing import List, Dict, Tuple, Optional
import os
import sumolib

def _is_driveable_edge(e: sumolib.net.edge.Edge, vclass: str = "passenger") -> bool:
    if e.getFunction() == "internal":
        return False
    return any(l.allows(vclass) for l in e.getLanes())

def _vec(p, q):
    return (q[0] - p[0], q[1] - p[1])

def _angle_deg(v1, v2) -> float:
    # devuelve el ángulo (0..180) entre v1 y v2
    x1, y1 = v1; x2, y2 = v2
    dot = x1*x2 + y1*y2
    n1 = math.hypot(x1, y1) or 1e-9
    n2 = math.hypot(x2, y2) or 1e-9
    c = max(-1.0, min(1.0, dot/(n1*n2)))
    return math.degrees(math.acos(c))

def _turn_sign(v1, v2) -> float:
    # signo del giro: >0 "izquierda" (aprox.), <0 "derecha"
    x1, y1 = v1; x2, y2 = v2
    return x1*y2 - y1*x2

class RoutePlanner:
    """
    Planner sobre nodos del .net.xml de SUMO.
    - BFS (coste unitario)
    - UCS (distancia) / UCS por tiempo (longitud/velocidad)
    - GREEDY (heurística euclídea)
    Evita U-turn inmediatos entre segmentos y puede penalizar giros a la izquierda.
    """
    def __init__(self, net_path: str, vclass: str = "passenger"):
        if not os.path.exists(net_path):
            raise FileNotFoundError(f"Net file not found: {net_path}")
        self.net = sumolib.net.readNet(net_path)
        self.vclass = vclass
        self._node_pos: Dict[str, Tuple[float, float]] = {
            n.getID(): n.getCoord() for n in self.net.getNodes()
        }

    # ---------- helpers ----------
    def _neighbors(self, node_id: str) -> List[Tuple[str, str]]:
        node = self.net.getNode(node_id)
        out_list: List[Tuple[str, str]] = []
        for e in node.getOutgoing():
            if not _is_driveable_edge(e, self.vclass):
                continue
            to_id = e.getToNode().getID()
            out_list.append((to_id, e.getID()))
        return out_list

    def _edge_between(self, u: str, v: str) -> Optional[str]:
        u_node = self.net.getNode(u)
        for e in u_node.getOutgoing():
            if e.getToNode().getID() == v and _is_driveable_edge(e, self.vclass):
                return e.getID()
        return None

    def _heuristic(self, a: str, b: str) -> float:
        ax, ay = self._node_pos[a]
        bx, by = self._node_pos[b]
        return math.hypot(ax - bx, ay - by)

    def _reconstruct_edges(
        self,
        parents: Dict[Tuple[str, Optional[str]], Tuple[str, Optional[str]]],
        start: str,
        goal: str,
        last_state: Tuple[str, Optional[str]]
    ) -> List[str]:
        # parents lleva estados (node, prev_edge_id) -> (parent_node, parent_prev_edge)
        path_nodes = []
        cur = last_state
        while cur[0] != start:
            path_nodes.append(cur[0])
            cur = parents[cur]
        path_nodes.append(start)
        path_nodes.reverse()
        edge_ids: List[str] = []
        for u, v in zip(path_nodes[:-1], path_nodes[1:]):
            e = self._edge_between(u, v)
            if e is None:
                raise RuntimeError(f"Ruta inconsistente: no hay arista manejable {u}->{v}")
            edge_ids.append(e)
        return edge_ids

    def _edge_cost(self, eid: str, metric: str) -> float:
        e = self.net.getEdge(eid)
        if metric == "time":
            sp = max(e.getSpeed(), 0.1)  # m/s
            return e.getLength() / sp
        # distancia (m)
        return e.getLength()

    def _left_turn_penalty(
        self,
        prev_eid: Optional[str],
        next_eid: str,
        angle_thresh_deg: float = 20.0,
        penalty_s: float = 5.0
    ) -> float:
        if not prev_eid:
            return 0.0
        e_prev = self.net.getEdge(prev_eid)
        e_next = self.net.getEdge(next_eid)
        pA = e_prev.getFromNode().getCoord()
        pB = e_prev.getToNode().getCoord()
        pC = e_next.getFromNode().getCoord()
        pD = e_next.getToNode().getCoord()
        v1 = _vec(pA, pB)
        v2 = _vec(pC, pD)
        ang = _angle_deg(v1, v2)
        sgn = _turn_sign(v1, v2)
        # penaliza "izquierda" con giro apreciable; ignoramos casi recto
        if ang >= angle_thresh_deg and sgn > 0:
            return penalty_s
        return 0.0

    # ---------- algoritmos ----------
    def bfs(self, start: str, goal: str, forbid_first_back_node: Optional[str] = None) -> List[str]:
        from collections import deque
        if start == goal:
            return []
        q = deque([start])
        visited = {start}
        parents: Dict[str, str] = {}
        while q:
            u = q.popleft()
            for v, _eid in self._neighbors(u):
                if u == start and forbid_first_back_node and v == forbid_first_back_node:
                    continue
                if v in visited:
                    continue
                parents[v] = u
                if v == goal:
                    # reconstrucción simple (sin estados)
                    pe: Dict[Tuple[str, Optional[str]], Tuple[str, Optional[str]]] = {}
                    cur = (v, None)
                    while cur[0] != start:
                        prev = parents[cur[0]]
                        pe[(cur[0], None)] = (prev, None)
                        cur = (prev, None)
                    return self._reconstruct_edges(pe, start, goal, (v, None))
                visited.add(v)
                q.append(v)
        raise RuntimeError(f"No hay camino BFS entre {start} y {goal}")

    def ucs(
        self,
        start: str,
        goal: str,
        metric: str = "distance",
        forbid_first_back_node: Optional[str] = None,
        avoid_left: bool = False,
        left_penalty_s: float = 5.0
    ) -> List[str]:
        """
        Dijkstra con coste por 'distance' o 'time'; puede penalizar giros a la izquierda.
        El estado incluye nodo y edge previo para evaluar el giro.
        """
        if start == goal:
            return []
        start_state = (start, None)  # (node, prev_edge_id)
        pq: List[Tuple[float, Tuple[str, Optional[str]]]] = [(0.0, start_state)]
        best: Dict[Tuple[str, Optional[str]], float] = {start_state: 0.0}
        parents: Dict[Tuple[str, Optional[str]], Tuple[str, Optional[str]]] = {}

        while pq:
            g, (u, prev_eid) = heapq.heappop(pq)
            if u == goal:
                return self._reconstruct_edges(parents, start, goal, (u, prev_eid))
            if g > best.get((u, prev_eid), float("inf")):
                continue
            for v, eid in self._neighbors(u):
                if u == start and forbid_first_back_node and v == forbid_first_back_node:
                    continue
                step = self._edge_cost(eid, metric)
                if avoid_left:
                    step += self._left_turn_penalty(prev_eid, eid, penalty_s=left_penalty_s)
                new_state = (v, eid)
                ng = g + step
                if ng < best.get(new_state, float("inf")):
                    best[new_state] = ng
                    parents[new_state] = (u, prev_eid)
                    heapq.heappush(pq, (ng, new_state))
        raise RuntimeError(f"No hay camino UCS entre {start} y {goal}")

    def greedy(self, start: str, goal: str, forbid_first_back_node: Optional[str] = None) -> List[str]:
        if start == goal:
            return []
        pq = [(self._heuristic(start, goal), start)]
        parents: Dict[str, str] = {}
        seen = {start}
        while pq:
            _h, u = heapq.heappop(pq)
            if u == goal:
                pe: Dict[Tuple[str, Optional[str]], Tuple[str, Optional[str]]] = {}
                cur = (u, None)
                while cur[0] != start:
                    prev = parents[cur[0]]
                    pe[(cur[0], None)] = (prev, None)
                    cur = (prev, None)
                return self._reconstruct_edges(pe, start, goal, (u, None))
            for v, _eid in self._neighbors(u):
                if u == start and forbid_first_back_node and v == forbid_first_back_node:
                    continue
                if v in seen:
                    continue
                seen.add(v)
                parents[v] = u
                heapq.heappush(pq, (self._heuristic(v, goal), v))
        raise RuntimeError(f"No hay camino GREEDY entre {start} y {goal}")

    # ---------- público ----------
    def plan(
        self,
        nodes: List[str],
        algo: str = "ucs",
        metric: str = "distance",
        avoid_left: bool = False,
        left_penalty_s: float = 5.0
    ) -> List[str]:
        """
        Convierte [N0,N1,N2,...] a lista de edge IDs.
        - metric: 'distance' | 'time'
        - avoid_left: si True, añade penalización (left_penalty_s) a giros a la izquierda
        """
        if len(nodes) < 2:
            raise ValueError("Se requieren al menos 2 nodos")
        algo = algo.lower()
        all_edges: List[str] = []
        prev_last_edge_from: Optional[str] = None
        prev_last_edge_to: Optional[str] = None

        for a, b in zip(nodes[:-1], nodes[1:]):
            forbid = None
            if prev_last_edge_from and prev_last_edge_to and a == prev_last_edge_to:
                forbid = prev_last_edge_from

            if algo == "bfs":
                seg = self.bfs(a, b, forbid_first_back_node=forbid)
            elif algo == "greedy":
                seg = self.greedy(a, b, forbid_first_back_node=forbid)
            elif algo == "ucs":
                seg = self.ucs(
                    a, b,
                    metric=metric,
                    forbid_first_back_node=forbid,
                    avoid_left=avoid_left,
                    left_penalty_s=left_penalty_s
                )
            else:
                raise ValueError(f"Algoritmo no soportado: {algo}")

            if seg:
                last_e = self.net.getEdge(seg[-1])
                prev_last_edge_from = last_e.getFromNode().getID()
                prev_last_edge_to = last_e.getToNode().getID()
            else:
                prev_last_edge_from, prev_last_edge_to = None, a

            all_edges.extend(seg)

        self.verify_route_edges(all_edges)
        return all_edges

    def verify_route_edges(self, edge_ids: List[str]) -> None:
        for eid in edge_ids:
            e = self.net.getEdge(eid)
            if not _is_driveable_edge(e, self.vclass):
                raise RuntimeError(f"Edge no manejable: {eid}")
        for e1, e2 in zip(edge_ids[:-1], edge_ids[1:]):
            a = self.net.getEdge(e1).getToNode().getID()
            b = self.net.getEdge(e2).getFromNode().getID()
            if a != b:
                raise RuntimeError(f"Secuencia inválida {e1} -> {e2} (nodos {a}!={b})")
