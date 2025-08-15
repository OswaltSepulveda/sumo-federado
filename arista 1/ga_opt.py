import numpy as np
import random
from deap import base, creator, tools

def run_ga_opt(pop_size=50, generations=100, eval_fn=None, simconf=None):
    """
    - simconf: diccionario de configuración (SIMCONF) con llave "traffic"->"traffic_lights" y opcional "phases_per_tls"
    """
    if eval_fn is None or simconf is None:
        raise ValueError("run_ga_opt necesita eval_fn y simconf (pásalos desde eval_1)")

    # Estructura DEAP
    # Minimizar Fitness
    try:
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        creator.create("Individual", list, fitness=creator.FitnessMin)
    except Exception:
        # Si ya existen (ejecuciones repetidas en la misma sesión), ignorar
        pass

    toolbox = base.Toolbox()

    # Genoma
    tls_list = simconf.get("traffic", {}).get("traffic_lights", [])
    phase_per_tls = simconf.get("traffic", {}).get("phases_per_tls", 6)
    genome_length = len(tls_list) * phase_per_tls

    # Genomas aleatorios
    toolbox.register("attr_float", random.uniform, 10, 60)  # Duracion de 10-60s
    # Inicializamos individuos con la longitud correcta
    toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_float, genome_length)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    def eval_individual(individual):
        metrics = eval_fn(individual)
        # DEAP espera una tupla como fitness
        return (metrics["fitness"],)

    # Operadores arbitrarios
    toolbox.register("evaluate", eval_individual)
    toolbox.register("mate", tools.cxOnePoint)  # Cruce de un punto
    toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=5, indpb=0.1)  # Mutacion Gaussiana
    toolbox.register("select", tools.selRoulette)  # Seleccion de ruleta

    # Poblacion inicial
    pop = toolbox.population(n=pop_size)
    fitnesses = list(map(toolbox.evaluate, pop))
    for ind, fit in zip(pop, fitnesses):
        ind.fitness.values = fit

    # Evolucion
    for gen in range(generations):
        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))

        # Aplicar cruce y mutacion
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < 0.5:  # Probabilidad de cruce
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        for mutant in offspring:
            if random.random() < 0.2:  # Probabilidad de mutacion
                toolbox.mutate(mutant)
                del mutant.fitness.values

        # Evaluar offspring
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        pop[:] = offspring  # Reemplazo

    # Mejor individuo
    best_ind = tools.selBest(pop, 1)[0]
    best_metrics = eval_fn(best_ind)

    return best_ind, best_metrics
