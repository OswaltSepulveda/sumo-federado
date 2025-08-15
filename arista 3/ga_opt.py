import os
import numpy as np
import pandas as pd
from sumo_env import SumoEnv, TLS_IDS, GREEN_MIN, GREEN_MAX

# ------------------------------
# GA parámetros
# ------------------------------
POP = 20
GEN = 15
ELITE = 2
TOUR_K = 3
PX = 0.9
PM = 0.2
MUT_STD = 6.0     # s

# Cromosoma: (gNS, gEW, offset) x len(TLS_IDS)
GENE_PER_TLS = 3
DIM = len(TLS_IDS) * GENE_PER_TLS

GREEN_BOUNDS = (GREEN_MIN, GREEN_MAX)
OFFSET_BOUNDS = (0, 30)  # ajústalo a tu ciclo esperado

def init_individuo(rng):
    x = []
    for _ in TLS_IDS:
        gNS = rng.randint(GREEN_BOUNDS[0], GREEN_BOUNDS[1]+1)
        gEW = rng.randint(GREEN_BOUNDS[0], GREEN_BOUNDS[1]+1)
        off = rng.randint(OFFSET_BOUNDS[0], OFFSET_BOUNDS[1]+1)
        x.extend([gNS, gEW, off])
    return np.array(x, dtype=float)

def tournament(pop, fit, rng):
    idxs = rng.choice(len(pop), size=TOUR_K, replace=False)
    best = min(idxs, key=lambda i: fit[i])  # menor fitness es mejor
    return pop[best].copy()

def crossover(a, b, rng):
    if rng.rand() > PX:
        return a.copy(), b.copy()
    # uniforme
    mask = rng.rand(len(a)) < 0.5
    c1 = np.where(mask, a, b)
    c2 = np.where(mask, b, a)
    return c1, c2

def mutate(x, rng):
    if rng.rand() < PM:
        # mutación gaussiana por gen con límites
        for i in range(len(x)):
            x[i] += rng.randn() * MUT_STD
            # límites por posición
            if (i % GENE_PER_TLS) in (0,1):
                lo, hi = GREEN_BOUNDS
            else:
                lo, hi = OFFSET_BOUNDS
            x[i] = np.clip(x[i], lo, hi)
    return x

def main(seed=123, gui=False, tag="exp1"):
    rng = np.random.RandomState(seed)
    env = SumoEnv(gui=gui, seed=seed)

    pop = [init_individuo(rng) for _ in range(POP)]
    hist = []

    for g in range(GEN):
        fits = []
        metrics = []
        for i, ind in enumerate(pop):
            run_id = f"{tag}_g{g}_i{i}"
            res = env.evaluate(ind, run_id=run_id)
            fits.append(res["fitness"])
            metrics.append(res)

        # log generación
        df = pd.DataFrame(metrics)
        df["gen"] = g
        df["individual"] = list(range(len(pop)))
        os.makedirs("results", exist_ok=True)
        df.to_csv(f"results/{tag}_gen{g}_summary.csv", index=False)

        # ordena por fitness asc
        order = np.argsort(fits)
        pop = [pop[i] for i in order]
        fits = [fits[i] for i in order]

        hist.append({"gen": g, "best_fitness": fits[0], "mean_fitness": float(np.mean(fits))})

        # reproducción
        new_pop = pop[:ELITE]  # elitismo
        while len(new_pop) < POP:
            p1 = tournament(pop, fits, rng)
            p2 = tournament(pop, fits, rng)
            c1, c2 = crossover(p1, p2, rng)
            c1 = mutate(c1, rng)
            c2 = mutate(c2, rng)
            new_pop.extend([c1, c2])
        pop = new_pop[:POP]

    pd.DataFrame(hist).to_csv(f"results/{tag}_fitness_history.csv", index=False)
    print("Listo. Revisa la carpeta 'results/'.")

if __name__ == "__main__":
    main(gui=False, tag="arista3_ga")
