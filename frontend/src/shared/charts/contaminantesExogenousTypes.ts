/**
 * Tipos para datos exógenos de Emisiones Contaminantes Criterio (BC, CO, COVDM, NOx, PM10, PM2_5, SOx).
 *
 * A diferencia de ExogenousDataConfig (Refinerías), aquí los datos NO son
 * una sola categoría extra sino valores por contaminante que se SUMAN a las
 * series existentes en la gráfica.
 *
 * Las claves en `data` deben coincidir con el sufijo del código FUEL (sin el
 * prefijo "EMI").  Ej: "BC" → serie "EMIBC", "CO" → "EMICO", etc.
 */

export type ContaminantesScenarioData = {
  jobId: number;
  scenarioName: string;
  /**
   * Datos por contaminante.  Clave = nombre del contaminante (ej: "BC", "CO",
   * "COVDM", "NOx", "PM10", "PM2_5", "SOx").  Valor = pares [año, valor].
   */
  data: Record<string, Array<[number, number]>>;
};

export type ContaminantesExogenousConfig = {
  active: boolean;
  scenarios: ContaminantesScenarioData[];
};
