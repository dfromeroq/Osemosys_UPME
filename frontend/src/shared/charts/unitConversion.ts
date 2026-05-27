/**
 * Factores de conversión para unidades de energía.
 * La unidad base es PJ.
 */
export const UNIT_FACTORS: Record<string, number> = {
  PJ: 1,
  GW: 31.536,
  MW: 0.031536,
  TWh: 3.6,
  Gpc: 1.0095581216,
  MtCO2eq: 1,
  ktCO2eq: 0.001,
  kt: 0.001,
  '%': 1,
};

const EMISSION_MAP: Record<string, string> = {
  MtCO2eq: 'MtCO₂eq',
  ktCO2eq: 'ktCO₂eq',
};

export function unitDisplayLabel(un: string): string {
  return EMISSION_MAP[un] ?? un;
}

/**
 * Calcula el ratio de conversión de un1 a un2.
 * Retorna null si las unidades son iguales o no están reconocidas.
 */
export function getUnitConversionRatio(un1: string, un2: string): number | null {
  if (!un2 || un1 === un2) return null;
  const f1 = UNIT_FACTORS[un1];
  const f2 = UNIT_FACTORS[un2];
  if (f1 == null || f2 == null) return null;
  return f1 / f2;
}
