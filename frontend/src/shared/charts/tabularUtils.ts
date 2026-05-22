/**
 * Utilidades compartidas para parseo de datos tabulares estilo Excel.
 *
 * Extraídas de SyntheticSeriesEditor.tsx para reuso en ExogenousDataEditor.
 */

/**
 * Parsea texto tabular (TSV de Excel / Google Sheets) a matriz de strings.
 * Ignora filas completamente vacías al final.
 */
export function parseTabular(text: string): string[][] {
  const rows = text.replace(/\r\n/g, "\n").split("\n").map((r) => r.split("\t"));
  while (rows.length > 0 && rows[rows.length - 1]!.every((c) => c.trim() === "")) {
    rows.pop();
  }
  return rows;
}

/** Convierte string ("100", "1.5e3", "1,5", "   ") a number o NaN. */
export function parseNumber(raw: string | undefined): number {
  if (raw == null) return NaN;
  const cleaned = raw.trim().replace(/\s/g, "").replace(",", ".");
  if (cleaned === "") return NaN;
  return Number(cleaned);
}
