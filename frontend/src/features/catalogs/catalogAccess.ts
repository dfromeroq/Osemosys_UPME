import type { User } from "@/types/domain";

/** Usuario puede entrar al área Catálogos (al menos una pestaña admin). */
export function canAccessCatalogsArea(user: User | null | undefined): boolean {
  if (!user) return false;
  return Boolean(
    user.can_manage_catalogs ||
      user.can_manage_model_defaults ||
      user.can_manage_system_settings,
  );
}

export type CatalogPageTab =
  | "parameter"
  | "region"
  | "technology"
  | "fuel"
  | "emission"
  | "solver"
  | "model_defaults"
  | "solver_config";

export const CATALOG_ENTITY_TABS = [
  "parameter",
  "region",
  "technology",
  "fuel",
  "emission",
  "solver",
] as const;

export function visibleCatalogTabs(user: User | null | undefined): CatalogPageTab[] {
  const tabs: CatalogPageTab[] = [];
  if (user?.can_manage_catalogs) {
    tabs.push(...CATALOG_ENTITY_TABS);
  }
  if (user?.can_manage_model_defaults) {
    tabs.push("model_defaults");
  }
  if (user?.can_manage_system_settings) {
    tabs.push("solver_config");
  }
  return tabs;
}

export function parseCatalogTabParam(raw: string | null): CatalogPageTab | null {
  if (!raw) return null;
  const all: CatalogPageTab[] = [
    ...CATALOG_ENTITY_TABS,
    "model_defaults",
    "solver_config",
  ];
  return all.includes(raw as CatalogPageTab) ? (raw as CatalogPageTab) : null;
}
