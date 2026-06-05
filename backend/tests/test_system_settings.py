"""Tests del endpoint admin de configuración del solver."""

from __future__ import annotations

from app.api.v1.system_settings import _effective_solver_threads, _hardware_thread_limit, _to_public
from app.simulation.core.model_definition import _resolve_defaults


def test_effective_solver_threads_caps_by_hardware(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.system_settings._hardware_thread_limit",
        lambda: 16,
    )
    assert _effective_solver_threads(0) == 16
    assert _effective_solver_threads(18) == 16
    assert _effective_solver_threads(8) == 8


def test_effective_solver_threads_zero_uses_all_hardware(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.system_settings._hardware_thread_limit",
        lambda: 8,
    )
    assert _effective_solver_threads(0) == 8


def test_solver_settings_public_returns_resolved_config(db_session) -> None:
    public = _to_public(db_session)
    assert public.solver_threads >= 0
    assert public.highs_method in ("default", "choose", "simplex", "ipm", "ipx", "hipo")
    assert public.highs_use_direct is True


def test_hardware_thread_limit_is_positive() -> None:
    assert _hardware_thread_limit() >= 1


def test_resolve_defaults_merges_param_defaults_override() -> None:
    merged = _resolve_defaults({"discountrate": 0.99})
    assert merged["discountrate"] == 0.99
