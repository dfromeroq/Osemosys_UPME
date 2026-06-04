"""Tests del endpoint admin de configuración del solver."""

from __future__ import annotations

import app.api.v1.system_settings as system_settings_api
from app.api.v1.system_settings import _to_public
from app.simulation.core.model_definition import _resolve_defaults


def test_solver_settings_public_includes_hardware_limits(db_session, monkeypatch) -> None:
    monkeypatch.setattr(system_settings_api, "_hardware_thread_limit", lambda: 16)
    monkeypatch.setattr(system_settings_api, "_effective_solver_threads", lambda v: min(v, 16) if v > 0 else 16)
    public = _to_public(db_session, value=18, updated_at=None, updated_by_id=None)
    assert public.hardware_thread_limit == 16
    assert public.effective_threads_preview == 16
    assert public.solver_threads == 18


def test_solver_settings_public_zero_uses_all_hardware(db_session, monkeypatch) -> None:
    monkeypatch.setattr(system_settings_api, "_hardware_thread_limit", lambda: 8)
    monkeypatch.setattr(system_settings_api, "_effective_solver_threads", lambda v: 8 if v <= 0 else min(v, 8))
    public = _to_public(db_session, value=0, updated_at=None, updated_by_id=None)
    assert public.hardware_thread_limit == 8
    assert public.effective_threads_preview == 8


def test_resolve_defaults_merges_param_defaults_override() -> None:
    merged = _resolve_defaults({"discountrate": 0.99})
    assert merged["discountrate"] == 0.99
