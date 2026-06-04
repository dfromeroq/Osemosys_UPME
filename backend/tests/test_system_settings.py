"""Tests del endpoint admin de configuración del solver."""

from __future__ import annotations

from app.api.v1.system_settings import _to_public
from app.simulation.core import solver as solver_module


def test_solver_settings_public_includes_hardware_limits(db_session, monkeypatch) -> None:
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 16)
    public = _to_public(db_session, value=18, updated_at=None, updated_by_id=None)
    assert public.hardware_thread_limit == 16
    assert public.effective_threads_preview == 16
    assert public.solver_threads == 18


def test_solver_settings_public_zero_uses_all_hardware(db_session, monkeypatch) -> None:
    monkeypatch.setattr(solver_module, "_hardware_thread_limit", lambda: 8)
    public = _to_public(db_session, value=0, updated_at=None, updated_by_id=None)
    assert public.hardware_thread_limit == 8
    assert public.effective_threads_preview == 8
