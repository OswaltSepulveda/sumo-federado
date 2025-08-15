# ga_opt.py
import random
import numpy as np
import csv
import os
from datetime import datetime
from deap import base, creator, tools

# Importamos evaluate_genome desde sim_eval
from sim_eval import evaluate_genome

# NUEVO: run_ga_optimization ahora acepta sumo_binary y lo pasa a evaluate_genome
def run_ga_optimization(pop_size, generations, net_file, route_file, scenario, run_id, sumo_binary="sumo"):
    random.seed(42)

    # Configuración DEAP
    # Evitar re-definir creators si ya existen (útil si corres varias veces en misma sesión)
    try:
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    except Exception:
        pass
    try:
        creator.create("Individual", list, fitness=creator.FitnessMax)
    except Exception:
        pass

    toolbox = base.Toolbox()
    toolbox.register("attr_int", random.randint, 10, 60)  # Tiempos iniciales de fase
    toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_int, n=8)  # 8 genes por individuo
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("mate", tools.cxOnePoint)  # Cruce arbitrario
    toolbox.register("mutate", tools.mutGaussian, mu=35, sigma=10, indpb=0.2)  # Mutación arbitraria
    toolbox.register("select", tools.selRoulette)  # Selección arbitraria

    # Registrar evaluate como wrapper que pasa sumo_binary (NUEVO)
    def _evaluate(ind):
        genome = [int(x) for x in ind]
        # IMPORTANT: evaluate_genome devuelve fitness (float); DEAP espera una tupla
        return (evaluate_genome(genome, net_file, route_file, scenario, run_id, sumo_binary),)

    toolbox.register("evaluate", _evaluate)

    population = toolbox.population(n=pop_size)

    # Archivo summary por generación
    summary_file = f"summary_{scenario}_{run_id}.csv"
    with open(summary_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["scenario", "run_id", "generation", "best_fitness", "mean_fitness", "std_fitness"])
        writer.writeheader()

        for gen in range(1, generations + 1):
            # Evaluar población
            for ind in population:
                if not ind.fitness.valid:
                    ind.fitness.values = toolbox.evaluate(ind)

            # Métricas de generación
            fits = [ind.fitness.values[0] for ind in population]
            best = max(fits)
            mean = np.mean(fits)
            std = np.std(fits)
            writer.writerow({
                "scenario": scenario,
                "run_id": run_id,
                "generation": gen,
                "best_fitness": best,
                "mean_fitness": mean,
                "std_fitness": std
            })

            # Selección
            offspring = toolbox.select(population, len(population))
            offspring = list(map(toolbox.clone, offspring))

            # Cruce
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < 0.5:
                    toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values

            # Mutación: aplicar y recortar a [10,60]
            for mutant in offspring:
                if random.random() < 0.2:
                    toolbox.mutate(mutant)
                    for i, v in enumerate(mutant):
                        mutant[i] = max(10, min(60, int(v)))
                    del mutant.fitness.values

            population[:] = offspring

    print(f"GA terminado para escenario {scenario}. Resultados guardados.")
