# src/ga/optimizer.py
import random, json, os
from pathlib import Path
from typing import Dict, List
from .encoding import Individual, init_population, repair_individual, TLSBounds, clone_individual
from .selection import tournament, roulette, ranking
from .crossover import per_intersection_cx, intra_intersection_cx
from .mutation import mutate
from .fitness import run_metrics, compute_fitness_from_csv

def choose_selection(sel_cfg):
    t = sel_cfg["type"]
    if t == "tournament":
        return lambda pop, rng: tournament(pop, k=sel_cfg.get("tournament_k",3), rng=rng)
    if t == "roulette":
        return lambda pop, rng: roulette(pop, rng=rng)
    if t == "rank":
        return lambda pop, rng: ranking(pop, rng=rng)
    raise ValueError("unknown selection type")

def eval_individual(
    ind: Individual,
    cfg_path: str,
    steps: int,
    weights: Dict[str,float],
    penalties: Dict[str,float],
    bounds_map,
    compat_map,
    out_dir: str,
    rng: random.Random,
    scenario_yaml_path: str = None,   # <--- NUEVO (opcional)
):
    """
    Evalúa un individuo:
      1) Construye un plan TLS desde el genoma
      2) Repara y cuenta violaciones (rangos/compatibilidad)
      3) Aplica el plan vía CLI: tls_apply.py --plan-json ... --steps 0 [--scenario-yaml ...]
      4) Ejecuta métricas y computa fitness + penalizaciones
    """
    import subprocess
    from pathlib import Path

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # 1) Individual -> plan dict
    plan = {"tls": {}}
    for tid, tls in ind.genome.items():
        plan["tls"][tid] = {
            "offset": tls.offset,
            "phases": [
                {"active_approaches": p.active_approaches, "g": p.g, "y": p.y, "r": p.r}
                for p in tls.phases
            ],
        }

    # 2) Reparar y contar violaciones antes de aplicar
    violations = repair_individual(ind, bounds_map, compat_map)

    # 3) Persistir plan y aplicar con tls_apply.py (steps=0)
    tmp_plan = os.path.join(out_dir, "plan.json")
    with open(tmp_plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    cmd_apply = [
        "python", "src/tls/tls_apply.py",
        "--cfg", cfg_path,
        "--plan-json", tmp_plan,
        "--steps", "0",
        "--save-json-dir", out_dir,
    ]
    # Pasa compatibilidad desde YAML del escenario si está disponible
    if scenario_yaml_path:
        cmd_apply += ["--scenario-yaml", scenario_yaml_path]

    r = subprocess.run(cmd_apply)
    if r.returncode != 0:
        raise RuntimeError("tls_apply.py failed when applying plan")

    # 4) Correr métricas y calcular fitness
    csvs = run_metrics(cfg_path, steps=steps, out_dir=os.path.join(out_dir, "csv"))
    base_f = compute_fitness_from_csv(csvs, weights)

    # Penalizaciones por violaciones detectadas en el repair
    f = base_f + penalties.get("invalid_tls_w", 0.0) * violations
    return f, violations

def run_ga(
    tls_blueprint,
    cfg_path,
    ga_cfg,
    bounds_map,
    compat_map,
    results_dir="experiments/runs/ga",
    seed=42,
    scenario_yaml_path: str = None,   # <--- NUEVO (opcional)
):
    rng = random.Random(seed)
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    pop = init_population(ga_cfg["population_size"], tls_blueprint, seed=seed)
    select_op = choose_selection(ga_cfg["selection"])
    cx_type = ga_cfg["crossover"]["type"]
    cx_rate = ga_cfg["crossover"]["rate"]
    intra_frac = ga_cfg["crossover"].get("intra_swap_frac", 0.5)
    mut_rate = ga_cfg["mutation"]["rate"]
    jitter_t = ga_cfg["mutation"]["time_jitter_s"]
    jitter_o = ga_cfg["mutation"]["offset_jitter_s"]
    reorder_p = ga_cfg["mutation"]["reorder_prob"]
    clamp = ga_cfg["mutation"].get("clamp", True)

    best = None
    for gen in range(ga_cfg["generations"]):
        # evaluación
        for i, ind in enumerate(pop):
            run_dir = os.path.join(results_dir, f"gen_{gen}", f"ind_{i}")
            Path(run_dir).mkdir(parents=True, exist_ok=True)
            f, viol = eval_individual(
                ind,
                cfg_path=cfg_path,
                steps=ga_cfg["fitness"]["steps"],
                weights=ga_cfg["fitness"]["weights"],
                penalties=ga_cfg["fitness"]["penalties"],
                bounds_map=bounds_map,
                compat_map=compat_map,
                out_dir=run_dir,
                rng=rng,
                scenario_yaml_path=scenario_yaml_path,  # <--- pasa YAML del escenario
            )
            ind.fitness = f

        pop.sort(key=lambda x: x.fitness, reverse=True)
        best = pop[0] if best is None or pop[0].fitness > best.fitness else best
        print(f"[GEN {gen}] best={pop[0].fitness:.3f}  global_best={best.fitness:.3f}")

        # nueva población (elitismo)
        new_pop: List[Individual] = [clone_individual(pop[i]) for i in range(min(ga_cfg["elitism"], len(pop)))]

        # reproducción
        while len(new_pop) < len(pop):
            p1 = select_op(pop, rng); p2 = select_op(pop, rng)
            c1, c2 = clone_individual(p1), clone_individual(p2)
            if rng.random() < cx_rate:
                if cx_type == "per_intersection":
                    from .crossover import per_intersection_cx as CX
                    c1, c2 = CX(p1, p2, rng=rng)
                else:
                    from .crossover import intra_intersection_cx as CX
                    c1, c2 = CX(p1, p2, swap_frac=intra_frac, rng=rng)
            # mutación
            from .mutation import mutate as MUT
            MUT(c1, mut_rate, jitter_t, jitter_o, reorder_p, rng=rng)
            MUT(c2, mut_rate, jitter_t, jitter_o, reorder_p, rng=rng)
            new_pop.extend([c1, c2])

        pop = new_pop[:len(pop)]

    return best
