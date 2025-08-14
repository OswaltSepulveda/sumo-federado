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
ROOT_ABS := C:/Users/melio/OneDrive/Escritorio/Proyectos/semaforos-geneticos

# --- Args extra para SUMO (solo afecta a targets run-* y gui-*)
# Ejemplo: make run-grid_3x3 SUMO_ARGS="--time-to-teleport 1000"
SUMO_ARGS ?=

# --- Paths ---
MIN_SC := sumo/scenarios/minimal
MIN_NET := $(MIN_SC)/net.net.xml
MIN_ROU := $(MIN_SC)/routes.rou.xml
MIN_CFG := $(MIN_SC)/cfg.sumocfg

.PHONY: help
help:
	@echo "Targets:"
	@echo "  validate-sumo         - Verifica binarios de SUMO (sumo, sumo-gui, netconvert, duarouter)"
	@echo "  minimal-net           - Genera un escenario mínimo (grid 2x2) en $(MIN_SC)"
	@echo "  traci-test            - Ejecuta script de smoke test con TraCI sobre el escenario mínimo"
	@echo "  clean-minimal         - Borra artefactos del escenario mínimo"
	@echo "  build-*, run-*, gui-* - Construye/corre cada escenario"
	@echo "  regen-*-low           - Regenera rutas con demanda reducida (menos teleports)"
	@echo "  tls-apply-*           - Aplica planes TLS con tiempos de despeje más seguros"
	@echo ""
	@echo "TIP: puedes pasar SUMO_ARGS a run-*/gui-* (p.ej., --time-to-teleport 1000)."

.PHONY: validate-sumo
validate-sumo:
	@which sumo && sumo --version
	@which sumo-gui && sumo-gui --version || true
	@which netconvert && netconvert --version
	@which duarouter && duarouter --version

# 1) Red 2x2 con TLS estimados
$(MIN_NET):
	mkdir -p $(MIN_SC)
	netgenerate --grid --grid.number=2 --grid.length=200 --default.lanenumber=1 \
		--tls.guess --tls.default-type=static --output-file=$(MIN_NET)

# 2) Rutas con randomTrips.py (invoca duarouter internamente)
$(MIN_ROU): $(MIN_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" \
		-n $(MIN_NET) -r $(MIN_ROU) \
		-b 0 -e 300 --period 1.0 \
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
	@echo '  <time begin="0" end="300" step-length="1"/>' >> $(MIN_CFG)
	@echo '</configuration>' >> $(MIN_CFG)


.PHONY: minimal-net
minimal-net: $(MIN_CFG)
	@echo "Escenario minimo creado en $(MIN_SC)" 

.PHONY: traci-test
traci-test: $(MIN_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg $(ROOT_ABS)/$(MIN_CFG) --steps 100 

.PHONY: clean-minimal 
clean-minimal:
	@rm -f $(MIN_NET) $(MIN_ROU) $(MIN_CFG)

## ---------------------------------------------------------------------------------------------------------------------

# ========================= Escenarios 2.2 =========================
# Requiere que SUMO_HOME apunte a tu instalación de SUMO
# y que tengas randomTrips.py disponible.

# ---------- helpers ----------
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

# ==================== GRID 3x3 ====================
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
		-b 0 -e 600 --period 1.0 --seed 11 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'
$(GRID_CFG): $(GRID_NET) $(GRID_ROU)
	$(call WRITE_CFG_LONGFORM,$(GRID_CFG),$(ROOT_ABS)/$(GRID_NET),$(ROOT_ABS)/$(GRID_ROU),0,600)

# Demanda reducida (LOW)
.PHONY: regen-grid-low
regen-grid-low: $(GRID_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(GRID_NET) -r $(GRID_ROU) \
		-b 0 -e 600 --period 2.0 --seed 11 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-grid_3x3 run-grid_3x3 gui-grid_3x3 traci-grid_3x3 clean-grid_3x3
build-grid_3x3: $(GRID_CFG)
run-grid_3x3: $(GRID_CFG)
	sumo -c $(ROOT_ABS)/$(GRID_CFG) $(SUMO_ARGS)
gui-grid_3x3: $(GRID_CFG)
	sumo-gui -c $(ROOT_ABS)/$(GRID_CFG) $(SUMO_ARGS)
traci-grid_3x3: $(GRID_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg $(ROOT_ABS)/$(GRID_CFG) --steps 200
clean-grid_3x3:
	rm -f $(GRID_SC)/*.xml

# ==================== ARTERIAL (corredor con calles transversales) ====================
ART_SC := sumo/scenarios/arterial
ART_NET := $(ART_SC)/net.net.xml
ART_ROU := $(ART_SC)/routes.rou.xml
ART_CFG := $(ART_SC)/cfg.sumocfg
$(ART_NET):
	mkdir -p $(ART_SC)
	netgenerate --grid --grid.x-number=8 --grid.y-number=2 --grid.length=120 \
		--default.lanenumber=2 \
		--default-junction-type traffic_light \
		--tls.default-type=static \
		--output-file=$(ART_NET)
$(ART_ROU): $(ART_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(ART_NET) -r $(ART_ROU) \
		-b 0 -e 900 --period 0.8 --seed 12 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'
$(ART_CFG): $(ART_NET) $(ART_ROU)
	$(call WRITE_CFG_LONGFORM,$(ART_CFG),$(ROOT_ABS)/$(ART_NET),$(ROOT_ABS)/$(ART_ROU),0,900)

# Demanda reducida (LOW)
.PHONY: regen-arterial-low
regen-arterial-low: $(ART_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(ART_NET) -r $(ART_ROU) \
		-b 0 -e 900 --period 1.6 --seed 12 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-arterial run-arterial gui-arterial traci-arterial clean-arterial
build-arterial: $(ART_CFG)
run-arterial: $(ART_CFG)
	sumo -c $(ROOT_ABS)/$(ART_CFG) $(SUMO_ARGS)
gui-arterial: $(ART_CFG)
	sumo-gui -c $(ROOT_ABS)/$(ART_CFG) $(SUMO_ARGS)
traci-arterial: $(ART_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg $(ROOT_ABS)/$(ART_CFG) --steps 300
clean-arterial:
	rm -f $(ART_SC)/*.xml

# ==================== RING (anillo/radial) ====================
RING_SC := sumo/scenarios/ring
RING_NET := $(RING_SC)/net.net.xml
RING_ROU := $(RING_SC)/routes.rou.xml
RING_CFG := $(RING_SC)/cfg.sumocfg
$(RING_NET):
	mkdir -p $(RING_SC)
	netgenerate --grid --grid.x-number=1 --grid.y-number=8 --grid.length=100 \
		--default.lanenumber=1 \
		--default-junction-type traffic_light \
		--tls.default-type=static \
		--output-file=$(RING_NET)
$(RING_ROU): $(RING_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RING_NET) -r $(RING_ROU) \
		-b 0 -e 900 --period 1.2 --fringe-factor 3.0 --seed 21 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'
$(RING_CFG): $(RING_NET) $(RING_ROU)
	$(call WRITE_CFG_LONGFORM,$(RING_CFG),$(ROOT_ABS)/$(RING_NET),$(ROOT_ABS)/$(RING_ROU),0,900)

# Demanda reducida (LOW)
.PHONY: regen-ring-low
regen-ring-low: $(RING_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RING_NET) -r $(RING_ROU) \
		-b 0 -e 900 --period 2.4 --fringe-factor 3.0 --seed 21 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-ring run-ring gui-ring traci-ring clean-ring
build-ring: $(RING_CFG)
run-ring: $(RING_CFG)
	sumo -c $(ROOT_ABS)/$(RING_CFG) $(SUMO_ARGS)
gui-ring: $(RING_CFG)
	sumo-gui -c $(ROOT_ABS)/$(RING_CFG) $(SUMO_ARGS)
traci-ring: $(RING_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg $(ROOT_ABS)/$(RING_CFG) --steps 300
clean-ring:
	rm -f $(RING_SC)/*.xml

# ==================== DOWNTOWN (malla densa) ====================
DT_SC := sumo/scenarios/downtown
DT_NET := $(DT_SC)/net.net.xml
DT_ROU := $(DT_SC)/routes.rou.xml
DT_CFG := $(DT_SC)/cfg.sumocfg
$(DT_NET):
	mkdir -p $(DT_SC)
	netgenerate --grid --grid.x-number=6 --grid.y-number=6 --grid.length=100 \
		--default.lanenumber=1 \
		--default-junction-type traffic_light \
		--tls.default-type=static \
		--output-file=$(DT_NET)
$(DT_ROU): $(DT_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(DT_NET) -r $(DT_ROU) \
		-b 0 -e 1200 --period 0.7 --seed 31 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'
$(DT_CFG): $(DT_NET) $(DT_ROU)
	$(call WRITE_CFG_LONGFORM,$(DT_CFG),$(ROOT_ABS)/$(DT_NET),$(ROOT_ABS)/$(DT_ROU),0,1200)

# Demanda reducida (LOW)
.PHONY: regen-downtown-low
regen-downtown-low: $(DT_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(DT_NET) -r $(DT_ROU) \
		-b 0 -e 1200 --period 1.4 --seed 31 --validate \
		--trip-attributes 'departLane="best" departSpeed="max"'

.PHONY: build-downtown run-downtown gui-downtown traci-downtown clean-downtown
build-downtown: $(DT_CFG)
run-downtown: $(DT_CFG)
	sumo -c $(ROOT_ABS)/$(DT_CFG) $(SUMO_ARGS)
gui-downtown: $(DT_CFG)
	sumo-gui -c $(ROOT_ABS)/$(DT_CFG) $(SUMO_ARGS)
traci-downtown: $(DT_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg $(ROOT_ABS)/$(DT_CFG) --steps 400
clean-downtown:
	rm -f $(DT_SC)/*.xml

# ==================== RUSH-HOUR (picos AM/PM) ====================
RH_SC := sumo/scenarios/rushhour
RH_NET := $(RH_SC)/net.net.xml
RH_ROU_AM := $(RH_SC)/routes_morning.rou.xml
RH_ROU_OFF := $(RH_SC)/routes_offpeak.rou.xml
RH_ROU_PM := $(RH_SC)/routes_evening.rou.xml
RH_CFG := $(RH_SC)/cfg.sumocfg

$(RH_NET):
	mkdir -p $(RH_SC)
	netgenerate --grid --grid.x-number=6 --grid.y-number=6 --grid.length=120 \
		--default.lanenumber=2 \
		--default-junction-type traffic_light \
		--tls.default-type=static \
		--output-file=$(RH_NET)

$(RH_ROU_AM): $(RH_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RH_NET) -r $(RH_ROU_AM) \
		-b 0 -e 900 --period 0.5 --seed 41 --prefix am \
		--trip-attributes 'departLane="best" departSpeed="max"' --validate

$(RH_ROU_OFF): $(RH_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RH_NET) -r $(RH_ROU_OFF) \
		-b 900 -e 1800 --period 2.0 --seed 42 --prefix off \
		--trip-attributes 'departLane="best" departSpeed="max"' --validate

$(RH_ROU_PM): $(RH_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RH_NET) -r $(RH_ROU_PM) \
		-b 1800 -e 2700 --period 0.5 --seed 43 --prefix pm \
		--trip-attributes 'departLane="best" departSpeed="max"' --validate

$(RH_CFG): $(RH_NET) $(RH_ROU_AM) $(RH_ROU_OFF) $(RH_ROU_PM)
	@echo '<?xml version="1.0" encoding="UTF-8"?>' > $(RH_CFG)
	@echo '<configuration>' >> $(RH_CFG)
	@echo '  <input>' >> $(RH_CFG)
	@echo '    <net-file value="$(ROOT_ABS)/$(RH_NET)"/>' >> $(RH_CFG)
	@echo '    <route-files value="$(ROOT_ABS)/$(RH_ROU_AM) $(ROOT_ABS)/$(RH_ROU_OFF) $(ROOT_ABS)/$(RH_ROU_PM)"/>' >> $(RH_CFG)
	@echo '  </input>' >> $(RH_CFG)
	@echo '  <time begin="0" end="2700" step-length="1"/>' >> $(RH_CFG)
	@echo '</configuration>' >> $(RH_CFG)

# Demanda reducida (LOW) para las tres franjas
.PHONY: regen-rushhour-low
regen-rushhour-low: $(RH_NET)
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RH_NET) -r $(RH_ROU_AM) \
		-b 0 -e 900 --period 1.0 --seed 41 --prefix am \
		--trip-attributes 'departLane="best" departSpeed="max"' --validate
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RH_NET) -r $(RH_ROU_OFF) \
		-b 900 -e 1800 --period 3.0 --seed 42 --prefix off \
		--trip-attributes 'departLane="best" departSpeed="max"' --validate
	$(PYTHON) "$(SUMO_HOME)/tools/randomTrips.py" -n $(RH_NET) -r $(RH_ROU_PM) \
		-b 1800 -e 2700 --period 1.0 --seed 43 --prefix pm \
		--trip-attributes 'departLane="best" departSpeed="max"' --validate

.PHONY: build-rushhour run-rushhour gui-rushhour traci-rushhour clean-rushhour
build-rushhour: $(RH_CFG)
run-rushhour: $(RH_CFG)
	sumo -c $(ROOT_ABS)/$(RH_CFG) $(SUMO_ARGS)
gui-rushhour: $(RH_CFG)
	sumo-gui -c $(ROOT_ABS)/$(RH_CFG) $(SUMO_ARGS)
traci-rushhour: $(RH_CFG)
	$(PYTHON) src/sim/traci_smoke.py --cfg $(ROOT_ABS)/$(RH_CFG) --steps 500
clean-rushhour:
	rm -f $(RH_SC)/*.xml

# -------- batch helpers --------
.PHONY: build-all-scenarios run-all-headless regen-all-low
build-all-scenarios: build-grid_3x3 build-arterial build-ring build-downtown build-rushhour
run-all-headless: run-grid_3x3 run-arterial run-ring run-downtown run-rushhour
regen-all-low: regen-grid-low regen-arterial-low regen-ring-low regen-downtown-low regen-rushhour-low

# ==== 2.3 helpers: listar nodos e inyectar vehículos por escenario ====

# ---- GRID 3x3 ----
.PHONY: list-nodes-grid inject-grid-auto inject-grid-bfs inject-grid-greedy
list-nodes-grid:
	$(PYTHON) src/sim/list_nodes.py --net $(ROOT_ABS)/sumo/scenarios/grid_3x3/net.net.xml --limit 50

inject-grid-auto: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --algo ucs --auto-k 3 --steps 600

# Sustituye N1,N2,N3 por IDs reales (ver 'make list-nodes-grid')
inject-grid-bfs: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --algo bfs --nodes N1,N2,N3 --steps 600

inject-grid-greedy: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --algo greedy --auto-k 3 --steps 600


# ---- ARTERIAL ----
.PHONY: list-nodes-arterial inject-arterial-auto inject-arterial-bfs inject-arterial-greedy
list-nodes-arterial:
	$(PYTHON) src/sim/list_nodes.py --net $(ROOT_ABS)/sumo/scenarios/arterial/net.net.xml --limit 50

inject-arterial-auto: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg --algo ucs --auto-k 3 --steps 900

inject-arterial-bfs: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg --algo bfs --nodes N1,N2,N3 --steps 900

inject-arterial-greedy: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg --algo greedy --auto-k 3 --steps 900


# ---- RING (anillo) ----
.PHONY: list-nodes-ring inject-ring-auto inject-ring-bfs inject-ring-greedy
list-nodes-ring:
	$(PYTHON) src/sim/list_nodes.py --net $(ROOT_ABS)/sumo/scenarios/ring/net.net.xml --limit 50

inject-ring-auto: build-ring
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg --algo ucs --auto-k 3 --steps 900

inject-ring-bfs: build-ring
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg --algo bfs --nodes N1,N2,N3 --steps 900

inject-ring-greedy: build-ring
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg --algo greedy --auto-k 3 --steps 900


# ---- DOWNTOWN ----
.PHONY: list-nodes-downtown inject-downtown-auto inject-downtown-bfs inject-downtown-greedy
list-nodes-downtown:
	$(PYTHON) src/sim/list_nodes.py --net $(ROOT_ABS)/sumo/scenarios/downtown/net.net.xml --limit 60

inject-downtown-auto: build-downtown
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg --algo ucs --auto-k 3 --steps 1200

inject-downtown-bfs: build-downtown
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg --algo bfs --nodes N1,N2,N3 --steps 1200

inject-downtown-greedy: build-downtown
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg --algo greedy --auto-k 3 --steps 1200


# ---- RUSHHOUR (tres franjas) ----
.PHONY: list-nodes-rushhour inject-rushhour-auto inject-rushhour-bfs inject-rushhour-greedy
list-nodes-rushhour:
	$(PYTHON) src/sim/list_nodes.py --net $(ROOT_ABS)/sumo/scenarios/rushhour/net.net.xml --limit 60

# auto-k 3: un vehículo demo; el escenario ya tiene rutas AM/OFF/PM cargadas
inject-rushhour-auto: build-rushhour
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg --algo ucs --auto-k 3 --steps 1500

inject-rushhour-bfs: build-rushhour
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg --algo bfs --nodes N1,N2,N3 --steps 1500

inject-rushhour-greedy: build-rushhour
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg --algo greedy --auto-k 3 --steps 1500


# ---- batch útil ----
.PHONY: inject-all-auto
inject-all-auto: inject-grid-auto inject-arterial-auto inject-ring-auto inject-downtown-auto inject-rushhour-auto

# ==== 2.3: variantes GUI ====

# GRID
.PHONY: inject-grid-auto-gui inject-grid-bfs-gui inject-grid-greedy-gui
inject-grid-auto-gui: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --algo ucs --metric time --avoid-left --auto-k 3 --steps 600 --gui
inject-grid-bfs-gui: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --algo bfs --nodes N1,N2,N3 --steps 600 --gui
inject-grid-greedy-gui: build-grid_3x3
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --algo greedy --auto-k 3 --steps 600 --gui

# ARTERIAL
.PHONY: inject-arterial-auto-gui
inject-arterial-auto-gui: build-arterial
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg --algo ucs --metric time --avoid-left --auto-k 3 --steps 900 --gui

# RING
.PHONY: inject-ring-auto-gui
inject-ring-auto-gui: build-ring
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg --algo ucs --metric time --avoid-left --auto-k 3 --steps 900 --gui

# DOWNTOWN
.PHONY: inject-downtown-auto-gui
inject-downtown-auto-gui: build-downtown
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg --algo ucs --metric time --avoid-left --auto-k 3 --steps 1200 --gui

# RUSHHOUR
.PHONY: inject-rushhour-auto-gui
inject-rushhour-auto-gui: build-rushhour
	$(PYTHON) src/sim/traci_inject.py --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg --algo ucs --metric time --avoid-left --auto-k 3 --steps 1500 --gui

# ==== 2.4 métricas por escenario (carpetas dedicadas) + plots ====

.PHONY: metrics-grid plots-grid \
        metrics-arterial plots-arterial \
        metrics-ring plots-ring \
        metrics-downtown plots-downtown \
        metrics-rushhour plots-rushhour \
        metrics-all plots-all

# GRID 3x3
metrics-grid: build-grid_3x3
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg \
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
	  --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg \
	  --steps 1200 --print-every 50 \
	  --out-dir experiments/results/csv/arterial

plots-arterial: metrics-arterial
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/arterial \
	  --topk 6 --label arterial \
	  --out-dir experiments/results/figs

# RING
metrics-ring: build-ring
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg \
	  --steps 1200 --print-every 50 \
	  --out-dir experiments/results/csv/ring

plots-ring: metrics-ring
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/ring \
	  --topk 6 --label ring \
	  --out-dir experiments/results/figs

# DOWNTOWN
metrics-downtown: build-downtown
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg \
	  --steps 1500 --print-every 50 \
	  --out-dir experiments/results/csv/downtown

plots-downtown: metrics-downtown
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/downtown \
	  --topk 6 --label downtown \
	  --out-dir experiments/results/figs

# RUSHHOUR
metrics-rushhour: build-rushhour
	$(PYTHON) src/sim/traci_metrics.py \
	  --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg \
	  --steps 1800 --print-every 50 \
	  --out-dir experiments/results/csv/rushhour

plots-rushhour: metrics-rushhour
	$(PYTHON) src/vis/plot_queues_flow.py \
	  --csv-dir experiments/results/csv/rushhour \
	  --topk 6 --label rushhour \
	  --out-dir experiments/results/figs

# Batch helpers
metrics-all: metrics-grid metrics-arterial metrics-ring metrics-downtown metrics-rushhour
plots-all: plots-grid plots-arterial plots-ring plots-downtown plots-rushhour

# ==== 2.5 TLS: inspección y aplicación de planes ====
# Ajuste de tiempos de "clearance" (más seguros: yellow/red más largos)

.PHONY: tls-inspect-grid tls-apply-grid tls-apply-grid-gui
tls-inspect-grid: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --inspect-only

tls-apply-grid: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --green 12 --yellow 4 --red 2 --offset 0 --steps 600

tls-apply-grid-gui: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg --green 12 --yellow 4 --red 2 --offset 10 --steps 600 --gui

# Puedes duplicar para otros escenarios cambiando el cfg:
.PHONY: tls-apply-arterial tls-apply-arterial-gui \
        tls-apply-ring tls-apply-ring-gui \
        tls-apply-downtown tls-apply-downtown-gui \
        tls-apply-rushhour tls-apply-rushhour-gui

tls-apply-arterial: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg --green 14 --yellow 4 --red 3 --offset 0 --steps 900
tls-apply-arterial-gui: build-arterial
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/arterial/cfg.sumocfg --green 14 --yellow 4 --red 3 --offset 7 --steps 900 --gui

tls-apply-ring: build-ring
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg --green 10 --yellow 4 --red 2 --offset 0 --steps 900
tls-apply-ring-gui: build-ring
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/ring/cfg.sumocfg --green 10 --yellow 4 --red 2 --offset 5 --steps 900 --gui

tls-apply-downtown: build-downtown
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg --green 12 --yellow 4 --red 3 --offset 0 --steps 1200
tls-apply-downtown-gui: build-downtown
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/downtown/cfg.sumocfg --green 12 --yellow 4 --red 3 --offset 10 --steps 800 --gui

tls-apply-rushhour: build-rushhour
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg --green 12 --yellow 4 --red 2 --offset 0 --steps 1500
tls-apply-rushhour-gui: build-rushhour
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/rushhour/cfg.sumocfg --green 12 --yellow 4 --red 2 --offset 10 --steps 1000 --gui

.PHONY: tls-apply-grid-yaml tls-apply-grid-yaml-gui save-plans-grid test-tls

# Aplica planes desde YAML (grid)
tls-apply-grid-yaml: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg \
	  --plan-yaml configs/scenarios/grid_3x3.yaml --steps 600

tls-apply-grid-yaml-gui: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg \
	  --plan-yaml configs/scenarios/grid_3x3.yaml --steps 600 --gui

# Serializa a JSON todos los TLS al aplicar
save-plans-grid: build-grid_3x3
	$(PYTHON) src/tls/tls_apply.py --cfg $(ROOT_ABS)/sumo/scenarios/grid_3x3/cfg.sumocfg \
	  --plan-yaml configs/scenarios/grid_3x3.yaml --steps 0 --save-json-dir configs/generated/grid_3x3

# Tests mínimos (requiere pytest)
test-tls:
	pytest -q tests/test_constraints.py


# ==== 2.6 Baselines ====

.PHONY: baseline-grid-static baseline-grid-coord baseline-grid-both
baseline-grid-static: build-grid_3x3
	$(PYTHON) src/eval/run_baselines.py --scenario grid_3x3 --plan static_fallback

baseline-grid-coord: build-grid_3x3
	$(PYTHON) src/eval/run_baselines.py --scenario grid_3x3 --plan coordinated

baseline-grid-both: build-grid_3x3
	$(PYTHON) src/eval/run_baselines.py --scenario grid_3x3 --plan both

.PHONY: baseline-arterial-both baseline-ring-both baseline-downtown-both baseline-rushhour-both baseline-all
baseline-arterial-both: build-arterial
	$(PYTHON) src/eval/run_baselines.py --scenario arterial --plan both
baseline-ring-both: build-ring
	$(PYTHON) src/eval/run_baselines.py --scenario ring --plan both
baseline-downtown-both: build-downtown
	$(PYTHON) src/eval/run_baselines.py --scenario downtown --plan both
baseline-rushhour-both: build-rushhour
	$(PYTHON) src/eval/run_baselines.py --scenario rushhour --plan both

baseline-all: baseline-grid-both baseline-arterial-both baseline-ring-both baseline-downtown-both baseline-rushhour-both

# ==== 2.6 Agregación de KPIs (darle una lista de carpetas csv) ====
# Ejemplo de uso:
# make kpis-compare CSV_DIRS="experiments/baselines/grid_3x3/static_fallback/*/csv experiments/baselines/grid_3x3/coordinated/*/csv"
.PHONY: kpis-compare
kpis-compare:
	$(PYTHON) src/eval/aggregate_metrics.py --csv-dirs $(CSV_DIRS) --out-csv experiments/baselines/kpis_comparativa.csv

