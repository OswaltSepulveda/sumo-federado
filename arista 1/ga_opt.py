# ga_opt.py
import numpy as np
import random
from deap import base, creator, tools

def run_ga_opt(pop_size, generations, eval_fn, simconf):
    # DEAP 
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    creator.create("Individual", np.ndarray, fitness=creator.FitnessMin)
    
    # Genoma
    toolbox = base.Toolbox()
    tls_list = simconf["traffic"]["traffic_lights"]
    phases_per_tls = simconf["traffic"]["phases_per_tls"]
    genome_length = len(tls_list) * phases_per_tls
    
    # Genomas aleatorios
    toolbox.register("attr_float", random.uniform, 10, 60) # 10 - 60 segundos
    toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_float, genome_length)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # Evaluacion
    def eval_individual(ind, gen_idx, ind_idx):
        metrics = eval_fn(ind, gen_num=gen_idx, ind_num=ind_idx)
        return (metrics["fitness"],)

    # Operadores arbitrarios
    toolbox.register("mate", tools.cxOnePoint) # Cruce de un punto
    toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=5, indpb=0.1) # Mutacion Gaussiana
    toolbox.register("select", tools.selRoulette) # Seleccion de Ruleta

    # Poblacion inicial
    pop = toolbox.population(n=pop_size)
    for i, ind in enumerate(pop):
        ind.fitness.values = eval_individual(ind, 0, i+1)

    # Evolucion
    for gen in range(1, generations + 1):
        print(f"[GA] Generación {gen}/{generations}")
        offspring = toolbox.select(pop, len(pop))
        offspring = list(map(toolbox.clone, offspring))

        # Cruce
        for child1, child2 in zip(offspring[::2], offspring[1::2]):
            if random.random() < 0.5: # Probabilidad de cruce
                toolbox.mate(child1, child2)
                del child1.fitness.values
                del child2.fitness.values

        # Mutacion
        for mutant in offspring:
            if random.random() < 0.2: # Probabilidad de mutacion
                toolbox.mutate(mutant)
                del mutant.fitness.values

        # Evaluar offspring
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        for idx, ind in enumerate(invalid_ind):
            ind.fitness.values = eval_individual(ind, gen, idx+1)

        pop[:] = offspring # Reemplazo
        
    # Mejor individuo
    best_ind = tools.selBest(pop, 1)[0]
    best_metrics = eval_fn(best_ind, gen_num=generations, ind_num=0)
    return best_ind, best_metrics
