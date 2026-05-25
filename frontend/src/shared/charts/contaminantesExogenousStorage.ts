/**
 * Persistencia local de datos exógenos para contaminantes criterio.
 *
 * Mismo patrón que exogenousDataStorage.ts pero con prefijo propio.
 */
import type { ContaminantesExogenousConfig } from "./contaminantesExogenousTypes";

const PREFIX = "osemosys:contaminantes-exogenous:";
const MAX_PAYLOAD_BYTES = 512 * 1024;

export function contaminantesExogenousSignature(parts: {
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

export function loadContaminantesExogenousData(
  signature: string,
): ContaminantesExogenousConfig | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(PREFIX + signature);
    if (!raw) return null;
    return JSON.parse(raw) as ContaminantesExogenousConfig;
  } catch (err) {
    console.warn("No se pudieron cargar datos exógenos (contaminantes):", err);
    return null;
  }
}

export function saveContaminantesExogenousData(
  signature: string,
  data: ContaminantesExogenousConfig | null,
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
        `Datos exógenos contaminantes demasiado grandes (${payload.length} bytes), omitiendo persistencia.`,
      );
      return;
    }
    window.localStorage.setItem(PREFIX + signature, payload);
  } catch (err) {
    console.warn("No se pudieron guardar datos exógenos (contaminantes):", err);
  }
}
