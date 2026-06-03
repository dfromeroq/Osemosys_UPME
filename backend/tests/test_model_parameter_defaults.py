from __future__ import annotations

from app.simulation.core.model_definition import create_abstract_model
from app.simulation.core.osemosys_defaults import (
    get_param_default,
    reset_defaults_context,
    set_defaults_context,
)


def test_create_abstract_model_accepts_param_defaults_override() -> None:
    model = create_abstract_model(
        has_storage=False,
        has_udc=False,
        param_defaults={"discountrate": 0.99},
    )
    assert model.DiscountRate.default == 0.99


def test_get_param_default_uses_context() -> None:
    token = set_defaults_context({"discountrate": 0.42})
    try:
        assert get_param_default("DiscountRate") == 0.42
    finally:
        reset_defaults_context(token)
