SHELL := /bin/bash
PYTHON ?= python

# --- SUMO env (override if needed) ---
export SUMO_HOME ?= /usr/share/sumo
export PYTHONPATH := $(SUMO_HOME)/tools:$(PYTHONPATH)

# --- Cross-platform null device (no lo usamos aquí, pero queda por si luego hace falta) ---
ifeq ($(OS),Windows_NT)
  NULLDEV := NUL
else
  NULLDEV := /dev/null
endif

# --- Root absoluto del repo (AJUSTA si cambias de PC/carpeta) ---
ROOT_ABS := C:/Users/Ismael Reyes/Documents/sumo-federado

# --- Args extra para SUMO (solo afecta a targets run-* y gui-*)
# Ejemplo: make run-grid_3x3 SUMO_ARGS="--time-to-teleport 1000"
SUMO_ARGS ?=

# --- Paths mínimos demo ---
MIN_SC := sumo/scenarios/minimal
MIN_NET := $(MIN_SC)/net.net.xml
MIN_ROU := $(MIN_SC)/routes.rou.xml
MIN_CFG := $(MIN_SC)/cfg.sumocfg

.PHONY: help
help:
	@echo "Targets:"
	@echo "  validate-sumo         - Verifica binarios de SUMO (sumo, sumo-gui, netconvert, duarouter)"
	@echo "  minimal-net           - Genera un escenario mínimo (grid 2x2) en $(MIN_SC)"
	@echo "  traci-test            - Smoke test con TraCI sobre el escenario mínimo"
	@echo "  clean-minimal         - Borra artefactos del escenario mínimo"
	@echo ""
	@echo "Escenarios (pequeños -> grandes):"
	@echo "  t_junction, cross_plus, grid_2x2, corridor_3x2, grid_3x3, arterial"
	@echo "  build-*, run-*, gui-*, traci-*, regen-*-low, clean-*"
	@echo ""
	@echo "Herramientas:"
	@echo "  list-nodes-*, inject-*-auto/bfs/greedy (+ variantes *-gui)"
	@echo "  tls-apply-*, tls-apply-*-gui, tls-apply-grid-yaml*, save-plans-grid, test-tls"
	@echo "  metrics-*, plots-*, metrics-all, plots-all"
	@echo "  baseline-*, baseline-all"
	@echo "  kpis-compare (agregación de métricas)"
	@echo ""
	@echo "Batch:"
	@echo "  build-all-scenarios, run-all-headless, regen-all-low, inject-all-auto"
	@echo ""
	@echo "TIP: pasa SUMO_ARGS a run-*/gui-* (p.ej., --time-to-teleport -1)."

.PHONY: validate-sumo
validate-sumo:
	@which sumo && sumo --version
	@which sumo-gui && sumo-gui --version || true
	@which netconvert && netconvert --version
	@which duarouter && duarouter --version

# ========================= DEMO MINIMAL =========================
# 1) Red 2x2 con TLS estimados (demo mínima)
$(MIN_NET):
	mkdir -p $(MIN_SC)
	netgenerate --grid --grid.number=2 --grid.length=180 --default.lanenumber=1 \
		--tls.guess --tls.default-type=static --output-file=$(MIN_NET)

# 2) Rutas low con randomTrips.py (menos autos)
$(MIN_ROU): $(MIN_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" \
		-n $(MIN_NET) -r $(MIN_ROU) \
		-b 0 -e 240 --period 3.0 \
		--trip-attributes 'departLane="best" departSpeed="max"' \
		--seed 42 --validate

# 3) Config .sumocfg con rutas ABSOLUTAS Windows (C:/...)
$(MIN_CFG): $(MIN_NET) $(MIN_ROU)
	@echo '<?xml version="1.0" encoding="UTF-8"?>' > $(MIN_CFG)
	@echo '<configuration>' >> $(MIN_CFG)
	@echo '  <input>' >> $(MIN_CFG)
	@echo '    <net-file value="$(ROOT_ABS)/$(MIN_NET)"/>' >> $(MIN_CFG)
	@echo '    <route-files value="$(ROOT_ABS)/$(MIN_ROU)"/>' >> $(MIN_CFG)
	@echo '  </input>' >> $(MIN_CFG)
	@echo '  <time begin="0" end="240" step-length="1"/>' >> $(MIN_CFG)
	@echo '</configuration>' >> $(MIN_CFG)

.PHONY: minimal-net
minimal-net: $(MIN_CFG)
	@echo "Escenario minimo creado en $(MIN_SC)"

.PHONY: traci-test
traci-test: $(MIN_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(MIN_CFG)" --steps 100

.PHONY: clean-minimal
clean-minimal:
	@rm -f $(MIN_NET) $(MIN_ROU) $(MIN_CFG)

## ---------------------------------------------------------------------------------------------------------------------
# ========================= Escenarios reducidos (6 total) =========================
# Orden: t_junction, cross_plus, grid_2x2, corridor_3x2, grid_3x3, arterial

# ---------- helper para escribir cfg ----------
define WRITE_CFG_LONGFORM
	@echo '<?xml version="1.0" encoding="UTF-8"?>' > $(1)
	@echo '<configuration>' >> $(1)
	@echo '  <input>' >> $(1)
	@echo '    <net-file value="$(2)"/>' >> $(1)
	@echo '    <route-files value="$(3)"/>' >> $(1)
	@echo '  </input>' >> $(1)
	@echo '  <time begin="$(4)" end="$(5)" step-length="1"/>' >> $(1)
	@echo '</configuration>' >> $(1)
endef

# ==================== 1) T-JUNCTION (1 semáforo, 3 brazos) ====================
T_SC := sumo/scenarios/t_junction
T_NET := $(T_SC)/net.net.xml
T_ROU := $(T_SC)/routes.rou.xml
T_CFG := $(T_SC)/cfg.sumocfg

$(T_NET):
	mkdir -p $(T_SC)
	netgenerate --spider --spider.arm-number=3 --spider.circle-number=1 --spider.space-radius=150 \
		--default.lanenumber=1 --default-junction-type traffic_light --tls.default-type=static \
		--output-file=$(T_NET)

$(T_ROU): $(T_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(T_NET) -r $(T_ROU) \
		-b 0 -e 300 --period 4.5 --seed 101 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

$(T_CFG): $(T_NET) $(T_ROU)
	$(call WRITE_CFG_LONGFORM,$(T_CFG),$(ROOT_ABS)/$(T_NET),$(ROOT_ABS)/$(T_ROU),0,300)

.PHONY: regen-t_junction-low
regen-t_junction-low: $(T_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(T_NET) -r $(T_ROU) \
		-b 0 -e 300 --period 6.0 --seed 101 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-t_junction run-t_junction gui-t_junction traci-t_junction clean-t_junction
build-t_junction: $(T_CFG)
run-t_junction: $(T_CFG)
	sumo -c "$(ROOT_ABS)/$(T_CFG)" $(SUMO_ARGS)
gui-t_junction: $(T_CFG)
	sumo-gui -c "$(ROOT_ABS)/$(T_CFG)" $(SUMO_ARGS)
traci-t_junction: $(T_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(T_CFG)" --steps 200
clean-t_junction:
	rm -f $(T_SC)/*.xml

# ==================== 2) CROSS PLUS (+) (1 semáforo, 4 brazos) ====================
X_SC := sumo/scenarios/cross_plus
X_NET := $(X_SC)/net.net.xml
X_ROU := $(X_SC)/routes.rou.xml
X_CFG := $(X_SC)/cfg.sumocfg

$(X_NET):
	mkdir -p $(X_SC)
	netgenerate --spider --spider.arm-number=4 --spider.circle-number=1 --spider.space-radius=150 \
		--default.lanenumber=1 --default-junction-type traffic_light --tls.default-type=static \
		--output-file=$(X_NET)

$(X_ROU): $(X_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(X_NET) -r $(X_ROU) \
		-b 0 -e 360 --period 4.0 --seed 102 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

$(X_CFG): $(X_NET) $(X_ROU)
	$(call WRITE_CFG_LONGFORM,$(X_CFG),$(ROOT_ABS)/$(X_NET),$(ROOT_ABS)/$(X_ROU),0,360)

.PHONY: regen-cross_plus-low
regen-cross_plus-low: $(X_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(X_NET) -r $(X_ROU) \
		-b 0 -e 360 --period 5.5 --seed 102 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-cross_plus run-cross_plus gui-cross_plus traci-cross_plus clean-cross_plus
build-cross_plus: $(X_CFG)
run-cross_plus: $(X_CFG)
	sumo -c "$(ROOT_ABS)/$(X_CFG)" $(SUMO_ARGS)
gui-cross_plus: $(X_CFG)
	sumo-gui -c "$(ROOT_ABS)/$(X_CFG)" $(SUMO_ARGS)
traci-cross_plus: $(X_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(X_CFG)" --steps 240
clean-cross_plus:
	rm -f $(X_SC)/*.xml

# ==================== 3) GRID 2x2 (malla mínima con varios TLS) ====================
G2_SC := sumo/scenarios/grid_2x2
G2_NET := $(G2_SC)/net.net.xml
G2_ROU := $(G2_SC)/routes.rou.xml
G2_CFG := $(G2_SC)/cfg.sumocfg

$(G2_NET):
	mkdir -p $(G2_SC)
	netgenerate --grid --grid.x-number=2 --grid.y-number=2 --grid.length=160 \
		--default.lanenumber=1 --default-junction-type traffic_light --tls.default-type=static \
		--output-file=$(G2_NET)

$(G2_ROU): $(G2_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(G2_NET) -r $(G2_ROU) \
		-b 0 -e 480 --period 3.5 --seed 103 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

$(G2_CFG): $(G2_NET) $(G2_ROU)
	$(call WRITE_CFG_LONGFORM,$(G2_CFG),$(ROOT_ABS)/$(G2_NET),$(ROOT_ABS)/$(G2_ROU),0,480)

.PHONY: regen-grid_2x2-low
regen-grid_2x2-low: $(G2_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(G2_NET) -r $(G2_ROU) \
		-b 0 -e 480 --period 5.0 --seed 103 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-grid_2x2 run-grid_2x2 gui-grid_2x2 traci-grid_2x2 clean-grid_2x2
build-grid_2x2: $(G2_CFG)
run-grid_2x2: $(G2_CFG)
	sumo -c "$(ROOT_ABS)/$(G2_CFG)" $(SUMO_ARGS)
gui-grid_2x2: $(G2_CFG)
	sumo-gui -c "$(ROOT_ABS)/$(G2_CFG)" $(SUMO_ARGS)
traci-grid_2x2: $(G2_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --steps 300
clean-grid_2x2:
	rm -f $(G2_SC)/*.xml

# ==================== 4) CORRIDOR 3x2 (estrecho y corto) ====================
C32_SC := sumo/scenarios/corridor_3x2
C32_NET := $(C32_SC)/net.net.xml
C32_ROU := $(C32_SC)/routes.rou.xml
C32_CFG := $(C32_SC)/cfg.sumocfg

$(C32_NET):
	mkdir -p $(C32_SC)
	netgenerate --grid --grid.x-number=3 --grid.y-number=2 --grid.length=140 \
		--default.lanenumber=1 --default-junction-type traffic_light --tls.default-type=static \
		--output-file=$(C32_NET)

$(C32_ROU): $(C32_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(C32_NET) -r $(C32_ROU) \
		-b 0 -e 600 --period 3.0 --seed 104 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

$(C32_CFG): $(C32_NET) $(C32_ROU)
	$(call WRITE_CFG_LONGFORM,$(C32_CFG),$(ROOT_ABS)/$(C32_NET),$(ROOT_ABS)/$(C32_ROU),0,600)

.PHONY: regen-corridor_3x2-low
regen-corridor_3x2-low: $(C32_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(C32_NET) -r $(C32_ROU) \
		-b 0 -e 600 --period 4.5 --seed 104 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-corridor_3x2 run-corridor_3x2 gui-corridor_3x2 traci-corridor_3x2 clean-corridor_3x2
build-corridor_3x2: $(C32_CFG)
run-corridor_3x2: $(C32_CFG)
	sumo -c "$(ROOT_ABS)/$(C32_CFG)" $(SUMO_ARGS)
gui-corridor_3x2: $(C32_CFG)
	sumo-gui -c "$(ROOT_ABS)/$(C32_CFG)" $(SUMO_ARGS)
traci-corridor_3x2: $(C32_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --steps 400
clean-corridor_3x2:
	rm -f $(C32_SC)/*.xml

# ==================== 5) GRID 3x3 (mediano) ====================
GRID_SC := sumo/scenarios/grid_3x3
GRID_NET := $(GRID_SC)/net.net.xml
GRID_ROU := $(GRID_SC)/routes.rou.xml
GRID_CFG := $(GRID_SC)/cfg.sumocfg

$(GRID_NET):
	mkdir -p $(GRID_SC)
	netgenerate --grid --grid.x-number=3 --grid.y-number=3 --grid.length=150 \
		--default.lanenumber=1 \
		--default-junction-type traffic_light \
		--tls.default-type=static \
		--output-file=$(GRID_NET)

$(GRID_ROU): $(GRID_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(GRID_NET) -r $(GRID_ROU) \
		-b 0 -e 600 --period 2.6 --seed 11 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

$(GRID_CFG): $(GRID_NET) $(GRID_ROU)
	$(call WRITE_CFG_LONGFORM,$(GRID_CFG),$(ROOT_ABS)/$(GRID_NET),$(ROOT_ABS)/$(GRID_ROU),0,600)

.PHONY: regen-grid_3x3-low
regen-grid_3x3-low: $(GRID_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(GRID_NET) -r $(GRID_ROU) \
		-b 0 -e 600 --period 3.6 --seed 11 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-grid_3x3 run-grid_3x3 gui-grid_3x3 traci-grid_3x3 clean-grid_3x3
build-grid_3x3: $(GRID_CFG)
run-grid_3x3: $(GRID_CFG)
	sumo -c "$(ROOT_ABS)/$(GRID_CFG)" $(SUMO_ARGS)
gui-grid_3x3: $(GRID_CFG)
	sumo-gui -c "$(ROOT_ABS)/$(GRID_CFG)" $(SUMO_ARGS)
traci-grid_3x3: $(GRID_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --steps 200
clean-grid_3x3:
	rm -f $(GRID_SC)/*.xml

# ==================== 6) ARTERIAL (corredor principal) ====================
ART_SC := sumo/scenarios/arterial
ART_NET := $(ART_SC)/net.net.xml
ART_ROU := $(ART_SC)/routes.rou.xml
ART_CFG := $(ART_SC)/cfg.sumocfg

$(ART_NET):
	mkdir -p $(ART_SC)
	netgenerate --grid --grid.x-number=6 --grid.y-number=2 --grid.length=120 \
		--default.lanenumber=2 \
		--default-junction-type traffic_light \
		--tls.default-type=static \
		--output-file=$(ART_NET)

$(ART_ROU): $(ART_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(ART_NET) -r $(ART_ROU) \
		-b 0 -e 900 --period 2.4 --seed 12 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

$(ART_CFG): $(ART_NET) $(ART_ROU)
	$(call WRITE_CFG_LONGFORM,$(ART_CFG),$(ROOT_ABS)/$(ART_NET),$(ROOT_ABS)/$(ART_ROU),0,900)

.PHONY: regen-arterial-low
regen-arterial-low: $(ART_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(ART_NET) -r $(ART_ROU) \
		-b 0 -e 900 --period 3.4 --seed 12 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-arterial run-arterial gui-arterial traci-arterial clean-arterial
build-arterial: $(ART_CFG)
run-arterial: $(ART_CFG)
	sumo -c "$(ROOT_ABS)/$(ART_CFG)" $(SUMO_ARGS)
gui-arterial: $(ART_CFG)
	sumo-gui -c "$(ROOT_ABS)/$(ART_CFG)" $(SUMO_ARGS)
traci-arterial: $(ART_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --steps 300
clean-arterial:
	rm -f $(ART_SC)/*.xml

# -------- batch helpers --------
.PHONY: build-all-scenarios run-all-headless regen-all-low
build-all-scenarios: build-t_junction build-cross_plus build-grid_2x2 build-corridor_3x2 build-grid_3x3 build-arterial
run-all-headless: run-t_junction run-cross_plus run-grid_2x2 run-corridor_3x2 run-grid_3x3 run-arterial
regen-all-low: regen-t_junction-low regen-cross_plus-low regen-grid_2x2-low regen-corridor_3x2-low regen-grid_3x3-low regen-arterial-low

# ========================= 2.3 helpers: listar nodos e inyectar vehículos =========================
# ---- T_JUNCTION ----
.PHONY: list-nodes-t inject-t-auto inject-t-bfs inject-t-greedy
list-nodes-t:
	$(PYTHON) src/sim/list_nodes.py --net "$(ROOT_ABS)/$(T_NET)" --limit 30
inject-t-auto: build-t_junction
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(T_CFG)" --algo ucs --auto-k 3 --steps 300
inject-t-bfs: build-t_junction
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(T_CFG)" --algo bfs --auto-k 3 --steps 300
inject-t-greedy: build-t_junction
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(T_CFG)" --algo greedy --auto-k 3 --steps 300

# ---- CROSS_PLUS ----
.PHONY: list-nodes-plus inject-plus-auto inject-plus-bfs inject-plus-greedy
list-nodes-plus:
	$(PYTHON) src/sim/list_nodes.py --net "$(ROOT_ABS)/$(X_NET)" --limit 30
inject-plus-auto: build-cross_plus
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(X_CFG)" --algo ucs --auto-k 3 --steps 360
inject-plus-bfs: build-cross_plus
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(X_CFG)" --algo bfs --auto-k 3 --steps 360
inject-plus-greedy: build-cross_plus
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(X_CFG)" --algo greedy --auto-k 3 --steps 360

# ---- GRID 2x2 ----
.PHONY: list-nodes-grid2 inject-grid2-auto inject-grid2-bfs inject-grid2-greedy
list-nodes-grid2:
	$(PYTHON) src/sim/list_nodes.py --net "$(ROOT_ABS)/$(G2_NET)" --limit 40
inject-grid2-auto: build-grid_2x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --algo ucs --auto-k 3 --steps 480
inject-grid2-bfs: build-grid_2x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --algo bfs --auto-k 3 --steps 480
inject-grid2-greedy: build-grid_2x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --algo greedy --auto-k 3 --steps 480

# ---- CORRIDOR 3x2 ----
.PHONY: list-nodes-corridor32 inject-corridor32-auto inject-corridor32-bfs inject-corridor32-greedy
list-nodes-corridor32:
	$(PYTHON) src/sim/list_nodes.py --net "$(ROOT_ABS)/$(C32_NET)" --limit 40
inject-corridor32-auto: build-corridor_3x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --algo ucs --auto-k 3 --steps 600
inject-corridor32-bfs: build-corridor_3x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --algo bfs --auto-k 3 --steps 600
inject-corridor32-greedy: build-corridor_3x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --algo greedy --auto-k 3 --steps 600

# ---- GRID 3x3 ----
.PHONY: list-nodes-grid inject-grid-auto inject-grid-bfs inject-grid-greedy
list-nodes-grid:
	$(PYTHON) src/sim/list_nodes.py --net "$(ROOT_ABS)/$(GRID_NET)" --limit 50
inject-grid-auto: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --algo ucs --auto-k 3 --steps 600
inject-grid-bfs: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --algo bfs --auto-k 3 --steps 600
inject-grid-greedy: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --algo greedy --auto-k 3 --steps 600

# ---- ARTERIAL ----
.PHONY: list-nodes-arterial inject-arterial-auto inject-arterial-bfs inject-arterial-greedy
list-nodes-arterial:
	$(PYTHON) src/sim/list_nodes.py --net "$(ROOT_ABS)/$(ART_NET)" --limit 50
inject-arterial-auto: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --algo ucs --auto-k 3 --steps 900
inject-arterial-bfs: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --algo bfs --auto-k 3 --steps 900
inject-arterial-greedy: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --algo greedy --auto-k 3 --steps 900

# ---- variantes GUI ----
.PHONY: inject-t-auto-gui inject-t-bfs-gui inject-t-greedy-gui \
        inject-plus-auto-gui inject-plus-bfs-gui inject-plus-greedy-gui \
        inject-grid2-auto-gui inject-grid2-bfs-gui inject-grid2-greedy-gui \
        inject-corridor32-auto-gui inject-corridor32-bfs-gui inject-corridor32-greedy-gui \
        inject-grid-auto-gui inject-grid-bfs-gui inject-grid-greedy-gui \
        inject-arterial-auto-gui

inject-t-auto-gui: build-t_junction
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(T_CFG)" --algo ucs --metric time --avoid-left --auto-k 3 --steps 300 --gui
inject-t-bfs-gui: build-t_junction
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(T_CFG)" --algo bfs --auto-k 3 --steps 300 --gui
inject-t-greedy-gui: build-t_junction
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(T_CFG)" --algo greedy --auto-k 3 --steps 300 --gui

inject-plus-auto-gui: build-cross_plus
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(X_CFG)" --algo ucs --metric time --avoid-left --auto-k 3 --steps 360 --gui
inject-plus-bfs-gui: build-cross_plus
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(X_CFG)" --algo bfs --auto-k 3 --steps 360 --gui
inject-plus-greedy-gui: build-cross_plus
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(X_CFG)" --algo greedy --auto-k 3 --steps 360 --gui

inject-grid2-auto-gui: build-grid_2x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --algo ucs --metric time --avoid-left --auto-k 3 --steps 480 --gui
inject-grid2-bfs-gui: build-grid_2x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --algo bfs --auto-k 3 --steps 480 --gui
inject-grid2-greedy-gui: build-grid_2x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --algo greedy --auto-k 3 --steps 480 --gui

inject-corridor32-auto-gui: build-corridor_3x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --algo ucs --metric time --avoid-left --auto-k 3 --steps 600 --gui
inject-corridor32-bfs-gui: build-corridor_3x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --algo bfs --auto-k 3 --steps 600 --gui
inject-corridor32-greedy-gui: build-corridor_3x2
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --algo greedy --auto-k 3 --steps 600 --gui

inject-grid-auto-gui: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --algo ucs --metric time --avoid-left --auto-k 3 --steps 600 --gui
inject-grid-bfs-gui: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --algo bfs --auto-k 3 --steps 600 --gui
inject-grid-greedy-gui: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --algo greedy --auto-k 3 --steps 600 --gui

inject-arterial-auto-gui: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --algo ucs --metric time --avoid-left --auto-k 3 --steps 900 --gui

# ---- batch útil ----
.PHONY: inject-all-auto
inject-all-auto: inject-t-auto inject-plus-auto inject-grid2-auto inject-corridor32-auto inject-grid-auto inject-arterial-auto

# ========================= 2.4 métricas por escenario + plots =========================
.PHONY: metrics-t plots-t \
        metrics-plus plots-plus \
        metrics-grid2 plots-grid2 \
        metrics-corridor32 plots-corridor32 \
        metrics-grid plots-grid \
        metrics-arterial plots-arterial \
        metrics-all plots-all

# T
metrics-t: build-t_junction
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg "$(ROOT_ABS)/$(T_CFG)" \
	  --steps 600 --print-every 50 \
	  --out-dir experiments/results/csv/t_junction

plots-t: metrics-t
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/t_junction \
	  --topk 4 --label t_junction \
	  --out-dir experiments/results/figs

# PLUS
metrics-plus: build-cross_plus
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg "$(ROOT_ABS)/$(X_CFG)" \
	  --steps 700 --print-every 50 \
	  --out-dir experiments/results/csv/cross_plus

plots-plus: metrics-plus
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/cross_plus \
	  --topk 4 --label cross_plus \
	  --out-dir experiments/results/figs

# GRID 2x2
metrics-grid2: build-grid_2x2
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg "$(ROOT_ABS)/$(G2_CFG)" \
	  --steps 900 --print-every 50 \
	  --out-dir experiments/results/csv/grid_2x2

plots-grid2: metrics-grid2
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/grid_2x2 \
	  --topk 6 --label grid_2x2 \
	  --out-dir experiments/results/figs

# CORRIDOR 3x2
metrics-corridor32: build-corridor_3x2
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg "$(ROOT_ABS)/$(C32_CFG)" \
	  --steps 900 --print-every 50 \
	  --out-dir experiments/results/csv/corridor_3x2

plots-corridor32: metrics-corridor32
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/corridor_3x2 \
	  --topk 6 --label corridor_3x2 \
	  --out-dir experiments/results/figs

# GRID 3x3
metrics-grid: build-grid_3x3
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg "$(ROOT_ABS)/$(GRID_CFG)" \
	  --steps 1200 --print-every 50 \
	  --out-dir experiments/results/csv/grid_3x3

plots-grid: metrics-grid
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/grid_3x3 \
	  --topk 6 --label grid_3x3 \
	  --out-dir experiments/results/figs

# ARTERIAL
metrics-arterial: build-arterial
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg "$(ROOT_ABS)/$(ART_CFG)" \
	  --steps 1200 --print-every 50 \
	  --out-dir experiments/results/csv/arterial

plots-arterial: metrics-arterial
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/arterial \
	  --topk 6 --label arterial \
	  --out-dir experiments/results/figs

# Batch helpers de métricas/plots
metrics-all: metrics-t metrics-plus metrics-grid2 metrics-corridor32 metrics-grid metrics-arterial
plots-all: plots-t plots-plus plots-grid2 plots-corridor32 plots-grid plots-arterial

# ========================= 2.5 TLS: inspección y aplicación de planes =========================
.PHONY: tls-inspect-t tls-apply-t tls-apply-t-gui \
        tls-inspect-plus tls-apply-plus tls-apply-plus-gui \
        tls-inspect-grid2 tls-apply-grid2 tls-apply-grid2-gui \
        tls-inspect-corridor32 tls-apply-corridor32 tls-apply-corridor32-gui \
        tls-inspect-grid tls-apply-grid tls-apply-grid-gui \
        tls-inspect-arterial tls-apply-arterial tls-apply-arterial-gui \
        tls-inspect-t-edges tls-inspect-plus-edges tls-inspect-grid2-edges \
        tls-inspect-corridor32-edges tls-inspect-grid-edges tls-inspect-arterial-edges \
        tls-scaffold-t tls-scaffold-plus tls-scaffold-grid2 tls-scaffold-corridor32 tls-scaffold-grid tls-scaffold-arterial \
        tls-apply-t-yaml tls-apply-t-yaml-gui save-plans-t \
        tls-apply-plus-yaml tls-apply-plus-yaml-gui save-plans-plus \
        tls-apply-grid2-yaml tls-apply-grid2-yaml-gui save-plans-grid2 \
        tls-apply-corridor32-yaml tls-apply-corridor32-yaml-gui save-plans-corridor32 \
        tls-apply-grid-yaml tls-apply-grid-yaml-gui save-plans-grid \
        tls-apply-arterial-yaml tls-apply-arterial-yaml-gui save-plans-arterial \
        test-tls

# ---------------- Básico (tu modo actual con tls_apply.py --inspect-only / tiempos directos) ----------------
# T
tls-inspect-t: build-t_junction
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(T_CFG)" --inspect-only
tls-apply-t: build-t_junction
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(T_CFG)" --green 12 --yellow 4 --red 2 --offset 0 --steps 300
tls-apply-t-gui: build-t_junction
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(T_CFG)" --green 12 --yellow 4 --red 2 --offset 5 --steps 300 --gui

# PLUS
tls-inspect-plus: build-cross_plus
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(X_CFG)" --inspect-only
tls-apply-plus: build-cross_plus
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(X_CFG)" --green 12 --yellow 4 --red 2 --offset 0 --steps 360
tls-apply-plus-gui: build-cross_plus
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(X_CFG)" --green 12 --yellow 4 --red 2 --offset 5 --steps 360 --gui

# GRID 2x2
tls-inspect-grid2: build-grid_2x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --inspect-only
tls-apply-grid2: build-grid_2x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --green 12 --yellow 4 --red 2 --offset 0 --steps 480
tls-apply-grid2-gui: build-grid_2x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --green 12 --yellow 4 --red 2 --offset 8 --steps 480 --gui

# CORRIDOR 3x2
tls-inspect-corridor32: build-corridor_3x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --inspect-only
tls-apply-corridor32: build-corridor_3x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --green 12 --yellow 4 --red 2 --offset 0 --steps 600
tls-apply-corridor32-gui: build-corridor_3x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --green 12 --yellow 4 --red 2 --offset 6 --steps 600 --gui

# GRID 3x3
tls-inspect-grid: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --inspect-only
tls-apply-grid: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --green 12 --yellow 4 --red 2 --offset 0 --steps 600
tls-apply-grid-gui: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --green 12 --yellow 4 --red 2 --offset 10 --steps 600 --gui

# ARTERIAL
tls-inspect-arterial: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --inspect-only
tls-apply-arterial: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --green 14 --yellow 4 --red 3 --offset 0 --steps 900
tls-apply-arterial-gui: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --green 14 --yellow 4 --red 3 --offset 7 --steps 900 --gui

# ---------------- Inspección detallada de aproximaciones (edges) y scaffolds YAML ----------------

tls-inspect-t-edges:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(T_CFG)"
tls-inspect-plus-edges:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(X_CFG)"
tls-inspect-grid2-edges:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(G2_CFG)"
tls-inspect-corridor32-edges:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(C32_CFG)"
tls-inspect-grid-edges:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(GRID_CFG)"
tls-inspect-arterial-edges:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(ART_CFG)"

tls-scaffold-t:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(T_CFG)" --save-yaml-scaffold configs/scenarios/t_junction.autogen.yaml
tls-scaffold-plus:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(X_CFG)" --save-yaml-scaffold configs/scenarios/cross_plus.autogen.yaml
tls-scaffold-grid2:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --save-yaml-scaffold configs/scenarios/grid_2x2.autogen.yaml
tls-scaffold-corridor32:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --save-yaml-scaffold configs/scenarios/corridor_3x2.autogen.yaml
tls-scaffold-grid:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --save-yaml-scaffold configs/scenarios/grid_3x3.autogen.yaml
tls-scaffold-arterial:
	$(PYTHON) src/tls/inspect_tls.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --save-yaml-scaffold configs/scenarios/arterial.autogen.yaml

# ---------------- Aplicación de YAML por escenario (coordinated) + guardado de JSON ----------------
tls-apply-t-yaml: build-t_junction
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(T_CFG)" --plan-yaml configs/scenarios/t_junction.yaml --steps 600
tls-apply-t-yaml-gui: build-t_junction
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(T_CFG)" --plan-yaml configs/scenarios/t_junction.yaml --steps 600 --gui
save-plans-t: build-t_junction
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(T_CFG)" --plan-yaml configs/scenarios/t_junction.yaml --steps 0 --save-json-dir configs/generated/t_junction

tls-apply-plus-yaml: build-cross_plus
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(X_CFG)" --plan-yaml configs/scenarios/cross_plus.yaml --steps 600
tls-apply-plus-yaml-gui: build-cross_plus
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(X_CFG)" --plan-yaml configs/scenarios/cross_plus.yaml --steps 600 --gui
save-plans-plus: build-cross_plus
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(X_CFG)" --plan-yaml configs/scenarios/cross_plus.yaml --steps 0 --save-json-dir configs/generated/cross_plus

tls-apply-grid2-yaml: build-grid_2x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --plan-yaml configs/scenarios/grid_2x2.yaml --steps 600
tls-apply-grid2-yaml-gui: build-grid_2x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --plan-yaml configs/scenarios/grid_2x2.yaml --steps 600 --gui
save-plans-grid2: build-grid_2x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(G2_CFG)" --plan-yaml configs/scenarios/grid_2x2.yaml --steps 0 --save-json-dir configs/generated/grid_2x2

tls-apply-corridor32-yaml: build-corridor_3x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --plan-yaml configs/scenarios/corridor_3x2.yaml --steps 600
tls-apply-corridor32-yaml-gui: build-corridor_3x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --plan-yaml configs/scenarios/corridor_3x2.yaml --steps 600 --gui
save-plans-corridor32: build-corridor_3x2
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(C32_CFG)" --plan-yaml configs/scenarios/corridor_3x2.yaml --steps 0 --save-json-dir configs/generated/corridor_3x2

tls-apply-grid-yaml: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --plan-yaml configs/scenarios/grid_3x3.yaml --steps 600
tls-apply-grid-yaml-gui: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --plan-yaml configs/scenarios/grid_3x3.yaml --steps 600 --gui
save-plans-grid: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(GRID_CFG)" --plan-yaml configs/scenarios/grid_3x3.yaml --steps 0 --save-json-dir configs/generated/grid_3x3

tls-apply-arterial-yaml: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --plan-yaml configs/scenarios/arterial.yaml --steps 900
tls-apply-arterial-yaml-gui: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --plan-yaml configs/scenarios/arterial.yaml --steps 900 --gui
save-plans-arterial: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg "$(ROOT_ABS)/$(ART_CFG)" --plan-yaml configs/scenarios/arterial.yaml --steps 0 --save-json-dir configs/generated/arterial

# ---------------- Tests de restricciones y consistencia ----------------
test-tls:
	pytest -q tests/test_constraints.py

# ========================= 2.6 Baselines =========================
.PHONY: baseline-plus baseline-t baseline-grid2 baseline-corridor32 baseline-grid3 baseline-arterial baseline-all
baseline-plus: build-cross_plus
	$(PYTHON) src/eval/run_baselines.py --scenario cross_plus --plan both
baseline-t: build-t_junction
	$(PYTHON) src/eval/run_baselines.py --scenario t_junction --plan both
baseline-grid2: build-grid_2x2
	$(PYTHON) src/eval/run_baselines.py --scenario grid_2x2 --plan both
baseline-corridor32: build-corridor_3x2
	$(PYTHON) src/eval/run_baselines.py --scenario corridor_3x2 --plan both
baseline-grid3: build-grid_3x3
	$(PYTHON) src/eval/run_baselines.py --scenario grid_3x3 --plan both
baseline-arterial: build-arterial
	$(PYTHON) src/eval/run_baselines.py --scenario arterial --plan both
baseline-all: baseline-plus baseline-t baseline-grid2 baseline-corridor32 baseline-grid3 baseline-arterial

# ========================= 2.6 Agregación de KPIs =========================
# Ejemplo:
# make kpis-compare CSV_DIRS="experiments/results/csv/t_junction experiments/results/csv/cross_plus"
.PHONY: kpis-compare
kpis-compare:
	$(PYTHON) src/eval/aggregate_metrics.py --csv-dirs $(CSV_DIRS) --out-csv experiments/baselines/kpis_comparativa.csv

# ==== 2.7 Optimización GA (módulo Python) ====

PYTHON ?= python

.PHONY: ga-t ga-plus ga-grid2 ga-corridor32 ga-grid ga-arterial

ga-t: build-t_junction
	$(PYTHON) -m src.cli.optimize \
	  --cfg sumo/scenarios/t_junction/cfg.sumocfg \
	  --scenario-yaml configs/scenarios/t_junction.yaml \
	  --ga-yaml configs/ga_default.yaml \
	  --results-dir experiments/runs/ga_t

ga-plus: build-cross_plus
	$(PYTHON) -m src.cli.optimize \
	  --cfg sumo/scenarios/cross_plus/cfg.sumocfg \
	  --scenario-yaml configs/scenarios/cross_plus.yaml \
	  --ga-yaml configs/ga_default.yaml \
	  --results-dir experiments/runs/ga_plus

ga-grid2: build-grid_2x2
	$(PYTHON) -m src.cli.optimize \
	  --cfg sumo/scenarios/grid_2x2/cfg.sumocfg \
	  --scenario-yaml configs/scenarios/grid_2x2.yaml \
	  --ga-yaml configs/ga_default.yaml \
	  --results-dir experiments/runs/ga_grid2

ga-corridor32: build-corridor_3x2
	$(PYTHON) -m src.cli.optimize \
	  --cfg sumo/scenarios/corridor_3x2/cfg.sumocfg \
	  --scenario-yaml configs/scenarios/corridor_3x2.yaml \
	  --ga-yaml configs/ga_default.yaml \
	  --results-dir experiments/runs/ga_corridor32

ga-grid: build-grid_3x3
	$(PYTHON) -m src.cli.optimize \
	  --cfg sumo/scenarios/grid_3x3/cfg.sumocfg \
	  --scenario-yaml configs/scenarios/grid_3x3.yaml \
	  --ga-yaml configs/ga_default.yaml \
	  --results-dir experiments/runs/ga_grid

ga-arterial: build-arterial
	$(PYTHON) -m src.cli.optimize \
	  --cfg sumo/scenarios/arterial/cfg.sumocfg \
	  --scenario-yaml configs/scenarios/arterial.yaml \
	  --ga-yaml configs/ga_default.yaml \
	  --results-dir experiments/runs/ga_arterial
