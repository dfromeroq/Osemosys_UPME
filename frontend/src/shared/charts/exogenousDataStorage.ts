/**
 * Persistencia local de datos exógenos por contexto de gráfica.
 *
 * Mismo patrón que syntheticSeriesStorage.ts: la clave es una "firma"
 * determinista que mezcla tipo/unidad/filtros/modo/job_ids — al cambiar
 * cualquiera de esos campos se cargan los datos guardados para la nueva
 * configuración (o null si no hay).
 */
import type { ExogenousDataConfig } from "@/types/domain";

const PREFIX = "osemosys:exogenous-data:";
const MAX_PAYLOAD_BYTES = 512 * 1024;

/**
 * Construye una firma determinista del contexto. Incluye job_ids para que
 * cambiar los escenarios seleccionados no herede datos de otro conjunto.
 */
export function exogenousDataSignature(parts: {
  tipo: string;
  un: string;
  agrupar_por?: string | null | undefined;
  job_ids_signature: string;
}): string {
  return [
    parts.tipo,
    parts.un,
    parts.agrupar_por ?? "",
    parts.job_ids_signature,
  ].join("|");
}

export function loadExogenousData(signature: string): ExogenousDataConfig | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(PREFIX + signature);
    if (!raw) return null;
    return JSON.parse(raw) as ExogenousDataConfig;
  } catch (err) {
    console.warn("No se pudieron cargar datos exógenos:", err);
    return null;
  }
}

export function saveExogenousData(
  signature: string,
  data: ExogenousDataConfig | null,
): void {
  if (typeof window === "undefined") return;
  try {
    if (!data) {
      window.localStorage.removeItem(PREFIX + signature);
      return;
    }
    const payload = JSON.stringify(data);
    if (payload.length > MAX_PAYLOAD_BYTES) {
      console.warn(
        `Datos exógenos demasiado grandes (${payload.length} bytes), omitiendo persistencia.`,
      );
      return;
    }
    window.localStorage.setItem(PREFIX + signature, payload);
  } catch (err) {
    console.warn("No se pudieron guardar datos exógenos:", err);
  }
}
