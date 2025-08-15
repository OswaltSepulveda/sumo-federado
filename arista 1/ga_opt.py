import numpy as np
import random
from deap import base, creator, tools
from eval_1 import evaluate_genome, SIMCONF

def run_ga_opt(pop_size=50, generations=100):
    
    # Estructura DEAP
    creator.create("FitnessMin", base.Fitness, weights=(-1.0)) # Minimizar Fitness
    creator.create("Individual", np.ndarray, fitness=creator.FitnessMin)
    
    toolbox = base.Toolbox()
    
    # Genoma
    tls_list = SIMCONF["traffic"]["traffic_lights"]
    phase_per_tls = 6
    genome_lenght = len(tls_list) * phase_per_tls
    
    # Genomas aleatorios
    toolbox.register("attr_float", random.uniform, 10, 60) # Duracion de 10-60s
    toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_float)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    
    def eval_individual(individual):
        metrics = evaluate_genome(individual)
        return metrics["fitness"]
    
    # Operadores arbitrarios
    toolbox.register("mate", tools.cxOnePoint) # Cruce de un punto
    toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=5, indpb=0.1) # Mutacion Gaussiana
    toolbox.register("select", tools.selRoulette) # Seleccion de ruleta
    
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
    best_metrics = evaluate_genome(best_ind)
    
    return best_ind, best_metrics
    
    