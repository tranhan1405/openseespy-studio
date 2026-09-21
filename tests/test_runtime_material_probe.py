from __future__ import annotations

from types import SimpleNamespace

import openseespy_studio.runtime as runtime


def test_legacy_frp_material_requires_targeted_runtime_probe():
    assert runtime.opensees_material_requires_runtime_probe(
        "FRPConfinedConcrete"
    )
    assert not runtime.opensees_material_requires_runtime_probe(
        "FRPConfinedConcrete02"
    )
    assert not runtime.opensees_material_requires_runtime_probe("Steel02")


def test_unknown_material_probe_is_a_noop():
    ok, detail = runtime.probe_opensees_material_support("Steel02")
    assert ok is True
    assert "No targeted runtime probe" in detail


def test_frp_runtime_probe_reports_compiled_out_material(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "opensees_python_requirement",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(runtime, "is_frozen_runtime", lambda: False)

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr=(
                "unreliable results, this material has been temporarily "
                "removed from the compiled versions of OpenSees (Tcl and Py)"
            ),
        )

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    ok, detail = runtime.probe_opensees_material_support(
        "FRPConfinedConcrete",
        python_executable="python",
    )

    assert ok is False
    assert "temporarily removed" in detail
    assert captured["command"][0] == "python"
    assert "FRPConfinedConcrete" in captured["command"][-1]


def test_frp_runtime_probe_accepts_supported_binary(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "opensees_python_requirement",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(runtime, "is_frozen_runtime", lambda: False)

    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="material=FRPConfinedConcrete: supported\n",
            stderr="",
        ),
    )

    ok, detail = runtime.probe_opensees_material_support(
        "FRPConfinedConcrete",
        python_executable="python",
    )

    assert ok is True
    assert "supported" in detail
