"""Tests de paridad del catálogo de visualización en BD."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.visualization.catalog_cache import get_catalog_cache, warm_catalog_cache
from app.visualization.catalog_reader import get_configs, get_menu
from app.visualization.configs_legacy import CONFIGS as LEGACY_CONFIGS


@pytest.fixture(autouse=True)
def _ensure_cache(db_session: Session) -> None:
    warm_catalog_cache(db_session)


def test_cache_has_chart_configs(db_session: Session) -> None:
    configs = get_configs()
    assert len(configs) >= len(LEGACY_CONFIGS) * 0.9
    assert "gas_consumo" in configs
    assert configs["gas_consumo"]["variable_default"] == LEGACY_CONFIGS["gas_consumo"]["variable_default"]


def test_menu_not_empty() -> None:
    menu = get_menu()
    assert len(menu) >= 1
    all_tipos = []
    for mod in menu:
        for c in mod.get("charts") or []:
            all_tipos.append(c["tipo"])
        for sub in mod.get("subs") or []:
            for c in sub.get("charts") or []:
                all_tipos.append(c["tipo"])
    assert len(all_tipos) >= 10


def test_filter_resolver_resolves_pwr(db_session: Session) -> None:
    cache = get_catalog_cache()
    techs = cache.filter_resolver.tech("TECNOLOGIAS_PWR")
    assert any(t.startswith("PWR") for t in techs)


def test_labels_from_cache(db_session: Session) -> None:
    cache = get_catalog_cache()
    assert cache.labels.get("PWRSOLRTP") or cache.labels.get("NGS")
