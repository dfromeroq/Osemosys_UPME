"""Motor de filtros declarativos para gráficas (grupos + composición)."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

FilterFn = Callable[..., pd.DataFrame]


class FilterResolver:
    """Resuelve códigos de grupos de filtro a conjuntos materializados."""

    def __init__(
        self,
        tech_groups: dict[str, frozenset[str]],
        fuel_groups: dict[str, frozenset[str]],
        subfiltro_maps: dict[str, dict[str, str]],
        valid_fuel_sets: dict[str, frozenset[str]],
    ) -> None:
        self._tech = tech_groups
        self._fuel = fuel_groups
        self._subfiltro_maps = subfiltro_maps
        self._valid_fuel_sets = valid_fuel_sets

    def tech(self, code: str) -> frozenset[str]:
        if code not in self._tech:
            raise KeyError(f"Grupo de tecnologías no encontrado: {code!r}")
        return self._tech[code]

    def fuel(self, code: str) -> frozenset[str]:
        if code not in self._fuel:
            raise KeyError(f"Grupo de combustibles no encontrado: {code!r}")
        return self._fuel[code]

    def subfiltro_group(self, dict_name: str, sub_code: str) -> frozenset[str]:
        mapping = self._subfiltro_maps.get(dict_name, {})
        group_code = mapping.get(sub_code)
        if group_code is None:
            return frozenset()
        return self.tech(group_code)

    def valid_fuels(self, code: str) -> frozenset[str]:
        return self._valid_fuel_sets.get(code, frozenset())


def build_filter_fn(spec: dict[str, Any], resolver: FilterResolver) -> FilterFn | None:
    """Construye callable compatible con ``filtro(df, sub_filtro=, loc=)``."""
    kind = spec.get("kind", "group")

    if kind == "group":
        group = spec["group"]
        entity = spec.get("entity", "TECHNOLOGY")

        def _fn(df: pd.DataFrame, **kw: Any) -> pd.DataFrame:
            if df.empty:
                return df
            codes = resolver.fuel(group) if entity == "FUEL" else resolver.tech(group)
            col = "FUEL" if entity == "FUEL" else "TECHNOLOGY"
            if col not in df.columns:
                return df.iloc[0:0]
            return df[df[col].isin(codes)]

        return _fn

    if kind == "sector_sub":
        root = spec["root_group"]
        sub_dict = spec["subfiltros_dict"]

        def _fn(df: pd.DataFrame, sub_filtro: str | None = None, **kw: Any) -> pd.DataFrame:
            if df.empty or "TECHNOLOGY" not in df.columns:
                return df.iloc[0:0]
            if sub_filtro:
                codes = resolver.subfiltro_group(sub_dict, sub_filtro)
                if not codes:
                    return df.iloc[0:0]
                return df[df["TECHNOLOGY"].isin(codes)]
            return df[df["TECHNOLOGY"].isin(resolver.tech(root))]

        return _fn

    if kind == "sector_sub_loc":
        root = spec["root_group"]
        sub_dict = spec["subfiltros_dict"]
        loc_groups = spec.get("loc_rules", spec.get("loc_groups", {}))

        def _fn(
            df: pd.DataFrame,
            sub_filtro: str | None = None,
            loc: str | None = None,
            **kw: Any,
        ) -> pd.DataFrame:
            if df.empty or "TECHNOLOGY" not in df.columns:
                return df.iloc[0:0]
            mask = df["TECHNOLOGY"].isin(resolver.tech(root))
            if sub_filtro:
                sub_codes = resolver.subfiltro_group(sub_dict, sub_filtro)
                if not sub_codes:
                    return df.iloc[0:0]
                mask &= df["TECHNOLOGY"].isin(sub_codes)
            if loc and loc in loc_groups:
                mask &= df["TECHNOLOGY"].isin(resolver.tech(loc_groups[loc]))
            return df[mask]

        return _fn

    if kind == "ref_ambas":
        tech_g = spec["tech_group"]
        fuel_ok = spec["fuel_con_crudo"]
        fuel_no = spec["fuel_sin_crudo"]

        def _fn(df: pd.DataFrame, sub_filtro: str | None = None, **kw: Any) -> pd.DataFrame:
            if df.empty or "TECHNOLOGY" not in df.columns or "FUEL" not in df.columns:
                return df.iloc[0:0]
            tech = resolver.tech(tech_g)
            fuels = resolver.fuel(fuel_no if sub_filtro == "sin_crudo" else fuel_ok)
            return df[df["TECHNOLOGY"].isin(tech) & df["FUEL"].isin(fuels)]

        return _fn

    if kind == "fuel_exclude_tech":
        fuel_g = spec["fuel_group"]
        ex_g = spec["exclude_tech_group"]

        def _fn(df: pd.DataFrame, **kw: Any) -> pd.DataFrame:
            if df.empty or "FUEL" not in df.columns or "TECHNOLOGY" not in df.columns:
                return df.iloc[0:0]
            return df[
                df["FUEL"].isin(resolver.fuel(fuel_g))
                & ~df["TECHNOLOGY"].isin(resolver.tech(ex_g))
            ]

        return _fn

    if kind == "recursos_carbon":
        tech_g = spec["tech_group"]
        fuel_g = spec["fuel_group"]
        ex_g = spec["exclude_tech_group"]

        def _fn(df: pd.DataFrame, **kw: Any) -> pd.DataFrame:
            if df.empty or "TECHNOLOGY" not in df.columns:
                return df.iloc[0:0]
            if "FUEL" in df.columns:
                return df[
                    df["TECHNOLOGY"].isin(resolver.tech(tech_g))
                    | (
                        df["FUEL"].str.startswith(tuple(resolver.fuel(fuel_g)))
                        & ~df["TECHNOLOGY"].isin(resolver.tech(ex_g))
                    )
                ]
            return df[df["TECHNOLOGY"].isin(resolver.tech(tech_g))]

        return _fn

    if kind == "demand_fuel":
        tech_g = spec["tech_group"]
        valid = spec["valid_fuels"]

        def _fn(df: pd.DataFrame, sub_filtro: str | None = None, **kw: Any) -> pd.DataFrame:
            if df.empty or "TECHNOLOGY" not in df.columns:
                return df.iloc[0:0]
            df = df[df["TECHNOLOGY"].isin(resolver.tech(tech_g))]
            if sub_filtro:
                if sub_filtro not in resolver.valid_fuels(valid):
                    return df.iloc[0:0]
                if "FUEL" not in df.columns:
                    return df.iloc[0:0]
                return df[df["FUEL"] == sub_filtro]
            return df

        return _fn

    if kind == "tech_and_fuel":
        fuel_g = spec["fuel_group"]
        tech_groups = spec.get("tech_groups")
        tech_g = spec.get("tech_group")

        def _tech_union() -> frozenset[str]:
            if tech_groups:
                out: set[str] = set()
                for g in tech_groups:
                    out.update(resolver.tech(g))
                return frozenset(out)
            return resolver.tech(str(tech_g))

        def _fn(df: pd.DataFrame, **kw: Any) -> pd.DataFrame:
            if df.empty or "TECHNOLOGY" not in df.columns or "FUEL" not in df.columns:
                return df.iloc[0:0]
            return df[
                df["TECHNOLOGY"].isin(_tech_union()) & df["FUEL"].isin(resolver.fuel(fuel_g))
            ]

        return _fn

    if kind == "startswith":

        def _fn(df: pd.DataFrame, sub_filtro: str | None = None, **kw: Any) -> pd.DataFrame:
            if not sub_filtro or df.empty or "TECHNOLOGY" not in df.columns:
                return df.iloc[0:0]
            return df[df["TECHNOLOGY"].str.startswith(sub_filtro)]

        return _fn

    raise ValueError(f"Tipo de filtro desconocido: {kind!r}")
