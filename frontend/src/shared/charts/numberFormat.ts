/**
 * Helpers de formato numérico para los ejes de las gráficas.
 *
 * `formatAxis3Sig`: formatea valores como enteros con separador de miles.
 * Misma lógica que el helper Python `format_axis_3sig` del backend (`chart_service.py`).
 */

/**
 * Suma `delta` puntos a una fontSize tipo "13px" o "13".
 * Si la entrada es indefinida o no parseable, retorna `undefined`.
 *
 * Útil para "amplificar" todas las tipografías de un chart de Highcharts
 * cuando se entra al modo de visualización ampliado (links compartibles).
 */
export function bumpFontSize(
  fontSize: string | undefined,
  delta: number,
): string | undefined {
  if (!fontSize) return undefined;
  const m = /^(\d+(?:\.\d+)?)(px|pt|em|rem)?$/.exec(fontSize.trim());
  if (!m) return fontSize;
  const value = Number(m[1]);
  if (!Number.isFinite(value)) return fontSize;
  const unit = m[2] ?? "px";
  return `${value + delta}${unit}`;
}

/**
 * Formatea un valor numérico para ejes de gráficas.
 *
 * Reglas:
 *   - |v| >= 10             → entero con separador de miles ("1,234")
 *   - 0 < |v| < 10          → 2 cifras significativas ("0.50", "1.0", "5.0")
 *   - 0                     → "0"
 */
export function formatAxis3Sig(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v as number)) return "0";
  const num = Number(v);
  if (num === 0) return "0";
  if (Math.abs(num) >= 10) {
    return num.toLocaleString("en-US", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
  }
  return num.toLocaleString("en-US", {
    minimumSignificantDigits: 2,
    maximumSignificantDigits: 2,
  });
}
