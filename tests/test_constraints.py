# tests/test_constraints.py
import os, sys, pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from tls.tls_model import (
    TLSPhaseSpec, TLSPlanSpec, build_program_states, validate_ranges
)

def fake_mapping(aplist):
    # construye mapping {i -> approach_id}
    return {i: ap for i, ap in enumerate(aplist)}

def test_single_active_without_compat():
    m = fake_mapping(["Ain","Bin","Cin"])
    plan = TLSPlanSpec("T", [TLSPhaseSpec(["Ain"], 10,3,1), TLSPhaseSpec(["Bin"], 10,3,1)])
    states = build_program_states(plan, m, compat_groups=None)
    # 2 fases * (G,y,r) = 6 estados
    assert len(states) == 6
    # Primera fase: un único verde
    state0, dur0 = states[0]
    assert state0.count("G") == 1
    assert pytest.approx(dur0, rel=1e-6) == 10.0  # duración del verde

def test_dual_active_needs_compat_ok():
    m = fake_mapping(["N","S","E","W"])
    # dos activas a la vez N y S (opuestas) -> permitirlo con compat declarada
    plan = TLSPlanSpec("T", [TLSPhaseSpec(["N","S"], 12,3,1)])
    comp = [["N","S"], ["E","W"]]
    states = build_program_states(plan, m, compat_groups=comp)
    assert states[0][0].count("G") == 2  # dos verdes simultáneos

def test_dual_active_without_compat_raises():
    m = fake_mapping(["N","S","E","W"])
    # dos activas a la vez sin compat -> debe fallar
    plan = TLSPlanSpec("T", [TLSPhaseSpec(["N","S"], 12,3,1)])
    with pytest.raises(ValueError):
        build_program_states(plan, m, compat_groups=None)

def test_dual_active_violates_compat():
    m = fake_mapping(["N","S","E","W"])
    plan = TLSPlanSpec("T", [TLSPhaseSpec(["N","E"], 12,3,1)])
    comp = [["N","S"], ["E","W"]]  # N&E no compatibles
    with pytest.raises(ValueError):
        build_program_states(plan, m, compat_groups=comp)

def test_validate_ranges_limits():
    m = fake_mapping(["A","B"])
    # Plan con green fuera de rango (ej. 100 > max_green=60 por defecto)
    bad = TLSPlanSpec("T", [TLSPhaseSpec(["A"], 100, 3, 1), TLSPhaseSpec(["B"], 10, 3, 1)])
    with pytest.raises(ValueError):
        validate_ranges(bad)  # usa límites por defecto
