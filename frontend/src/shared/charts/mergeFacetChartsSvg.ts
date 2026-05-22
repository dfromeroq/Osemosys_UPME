/**
 * Combina varios SVG generados por Highcharts.getSVG() en un solo documento,
 * renombrando ids para evitar colisiones (clipPath, gradientes, etc.).
 */

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Reasigna id y referencias url(#…) / href="#…" dentro de un fragmento SVG. */
export function remapSvgFragmentIds(svg: string, prefix: string): string {
  const re = /\bid="([^"]+)"/g;
  const found = new Set<string>();
  let m: RegExpExecArray | null;
  const copy = svg;
  while ((m = re.exec(copy)) !== null) {
    if (m[1]) found.add(m[1]);
  }
  const ids = [...found].sort((a, b) => b.length - a.length);
  let out = svg;
  for (const id of ids) {
    const p = `${prefix}${id}`;
    out = out.replaceAll(`id="${id}"`, `id="${p}"`);
    out = out.replaceAll(`url(#${id})`, `url(#${p})`);
    out = out.replaceAll(`url("#${id}")`, `url("#${p}")`);
    out = out.replaceAll(`href="#${id}"`, `href="#${p}"`);
    out = out.replaceAll(`xlink:href="#${id}"`, `xlink:href="#${p}"`);
  }
  return out;
}

export function extractSvgRootInnerXml(svg: string): string {
  const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = doc.documentElement;
  if (doc.querySelector("parsererror")) {
    throw new Error("No se pudo analizar el SVG exportado.");
  }
  return root.innerHTML;
}

export type FacetExportLegendItem = {
  name: string;
  color: string;
  /** Serie oculta en la UI (misma semántica que en la app). */
  hidden?: boolean;
};

/**
 * Bloque de leyenda bajo las gráficas (marcador + nombre, ajuste de línea).
 * `legendHeaderBaselineY` = línea base del título "LEYENDA…".
 */
function buildSharedLegendSvgBlock(
  items: FacetExportLegendItem[],
  totalW: number,
  paddingX: number,
  legendHeaderBaselineY: number,
): { fragment: string; blockBottomY: number } {
  if (items.length === 0) {
    return { fragment: "", blockBottomY: legendHeaderBaselineY };
  }

  const maxX = totalW - paddingX;
  let x = paddingX;
  let rowY = legendHeaderBaselineY + 18;
  const lineHeight = 22;
  const charW = 6.5;
  const markerSize = 10;
  const markerGap = 8;
  const itemPadX = 14;

  const parts: string[] = [];
  parts.push(
    `<text x="${paddingX}" y="${legendHeaderBaselineY}" fill="#64748b" font-size="20" font-weight="normal" font-family="Verdana, sans-serif" letter-spacing="0.06em">LEYENDA (TODAS LAS GRÁFICAS)</text>`,
  );

  for (const item of items) {
    const textW = Math.ceil(item.name.length * charW);
    const itemW = markerSize + markerGap + textW + 6;
    if (x + itemW > maxX && x > paddingX) {
      rowY += lineHeight;
      x = paddingX;
    }

    const opacity = item.hidden ? 0.55 : 1;
    const textFill = item.hidden ? "#94a3b8" : "#334155";
    const deco = item.hidden ? ' text-decoration="line-through"' : "";
    const nameEsc = escapeXml(item.name);
    const markFillEsc = escapeXml(item.hidden ? "#cbd5e1" : item.color);

    parts.push(`<g opacity="${opacity}">`);
    parts.push(
      `<rect x="${x}" y="${rowY - markerSize + 3}" width="${markerSize}" height="${markerSize}" rx="2" fill="${markFillEsc}" stroke="#cbd5e1" stroke-width="0.75"/>`,
    );
    parts.push(
      `<text x="${x + markerSize + markerGap}" y="${rowY}" fill="${textFill}" font-size="20" font-family="Verdana, sans-serif"${deco}>${nameEsc}</text>`,
    );
    parts.push(`</g>`);
    x += itemW + itemPadX;
  }

  const blockBottomY = rowY + lineHeight + 8;
  return { fragment: parts.join(""), blockBottomY };
}

export function buildCombinedFacetSvgDocument(params: {
  mainTitle: string;
  /** Contenido interno de cada <svg> raíz de Highcharts (sin el elemento svg exterior). */
  fragmentInnerXmls: string[];
  layout: "row" | "column";
  sliceW: number;
  sliceH: number;
  /** Leyenda compartida (mismo contenido que el panel React). */
  legendItems?: FacetExportLegendItem[];
  /** Nombres de cada faceta (escenario) para mostrar a la izquierda. */
  facetLabels?: string[];
}): string {
  const { mainTitle, fragmentInnerXmls, layout, sliceW, sliceH, legendItems, facetLabels } = params;
  const n = fragmentInnerXmls.length;
  const paddingX = 24;
  const gap = 16;
  const bottomPad = 24;
  const titleBaselineY = 60;
  const titleToChartsGap = 28;
  const chartsToLegendGap = 28;
  /** Ancho reservado para etiquetas de faceta a la izquierda (layout column). */
  const facetLabelWidth = 120;

  const totalW: number = (layout === "row")
    ? paddingX * 2 + n * sliceW + Math.max(0, n - 1) * gap
    : paddingX * 2 + facetLabelWidth + gap + sliceW;

  const chartStartY = titleBaselineY + titleToChartsGap;

  let chartsBottomY: number;
  let body = "";

  if (layout === "row") {
    let x = paddingX;
    for (let i = 0; i < n; i += 1) {
      const inner = fragmentInnerXmls[i]!;
      const rawLabel: string | undefined = facetLabels?.[i];
      const label: string = rawLabel ? escapeXml(rawLabel) : "";
      if (label) {
        body += `<text x="${x}" y="${chartStartY + sliceH / 2}" fill="#1e293b" font-size="22" font-weight="bold" font-family="Verdana, sans-serif" text-anchor="end" dominant-baseline="middle" transform="rotate(-90,${x},${chartStartY + sliceH / 2})">${label}</text>`;
      }
      body += `<g transform="translate(${x},${chartStartY})">${inner}</g>`;
      x += sliceW + gap;
    }
    chartsBottomY = chartStartY + sliceH;
  } else {
    let y = chartStartY;
    for (let i = 0; i < n; i += 1) {
      const inner = fragmentInnerXmls[i]!;
      const rawLabel: string | undefined = facetLabels?.[i];
      const label: string = rawLabel ? escapeXml(rawLabel) : "";
      if (label) {
        body += `<text x="${paddingX}" y="${y + sliceH / 2}" fill="#1e293b" font-size="22" font-weight="bold" font-family="Verdana, sans-serif" text-anchor="end" dominant-baseline="middle">${label}</text>`;
      }
      body += `<g transform="translate(${paddingX + facetLabelWidth + gap},${y})">${inner}</g>`;
      y += sliceH + gap;
    }
    chartsBottomY = chartStartY + (n - 1) * (sliceH + gap) + sliceH;
  }

  const legendHeaderY = chartsBottomY + chartsToLegendGap;
  const { fragment: legendFragment, blockBottomY } = buildSharedLegendSvgBlock(
    legendItems ?? [],
    totalW,
    paddingX,
    legendHeaderY,
  );

  const totalH =
    (legendItems?.length ? blockBottomY : chartsBottomY) + bottomPad;

  const titleEsc = escapeXml(mainTitle);

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}" style="font-family: Verdana, sans-serif; font-size: 1rem;" role="img" aria-label="${titleEsc}">
  <desc>Combined facet export (Highcharts)</desc>
  <rect fill="#FFFFFF" x="0" y="0" width="${totalW}" height="${totalH}" />
  <text x="${paddingX}" y="${titleBaselineY}" fill="#1e293b" font-size="36" font-weight="bold" font-family="Verdana, sans-serif">${titleEsc}</text>
  ${body}
  ${legendFragment}
</svg>`;
}
