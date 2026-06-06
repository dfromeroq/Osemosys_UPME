import type { ChartMenuModule } from './useChartMenu';

let cachedMenu: ChartMenuModule[] = [];

export function setChartMenuCache(menu: ChartMenuModule[]): void {
  cachedMenu = menu;
}

export function getChartMenuCache(): ChartMenuModule[] {
  return cachedMenu;
}
