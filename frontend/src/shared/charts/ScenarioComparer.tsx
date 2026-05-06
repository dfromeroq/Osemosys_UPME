import React from 'react';

export type CompareViewMode = 'facet' | 'by-year' | 'by-year-alt' | 'line-total';

interface ScenarioComparerProps {
  /** Cantidad de escenarios seleccionados en la tabla superior (incluye el actual). */
  selectedCount: number;
  selectedYears: number[];
  compareViewMode: CompareViewMode;
  onChangeViewMode: (mode: CompareViewMode) => void;
  onChangeYears: (years: number[]) => void;
}

const AVAILABLE_YEARS = [2022, 2024, 2025, 2030, 2035, 2040, 2045, 2050, 2054];

/**
 * Selector de modo de comparación (facet / by-year / line-total) y años a graficar
 * cuando aplica. La selección de escenarios vive en la tabla superior de
 * `ResultDetailPage` — este componente NO duplica esa selección.
 */
export const ScenarioComparer: React.FC<ScenarioComparerProps> = ({
  selectedCount,
  selectedYears,
  compareViewMode,
  onChangeViewMode,
  onChangeYears,
}) => {
  const handleYearToggle = (year: number) => {
    let newYears = [...selectedYears];
    if (newYears.includes(year)) {
      if (newYears.length <= 1) return;
      newYears = newYears.filter((y) => y !== year);
    } else {
      newYears.push(year);
      newYears.sort((a, b) => a - b);
    }
    onChangeYears(newYears);
  };

  const active = selectedCount >= 2;

  return (
    <div className="flex flex-col md:flex-row gap-4">
      <div className="bg-[#1e293b] p-4 rounded-xl border border-slate-700/50 flex-1">
        <div className="flex items-baseline justify-between mb-3">
          <span className="text-sm font-bold text-slate-300">
            Modo de comparación
          </span>
          <span className="text-xs text-slate-500">
            {active
              ? `${selectedCount} escenarios seleccionados en la tabla superior`
              : 'Selecciona 2 o más escenarios en la tabla superior para comparar'}
          </span>
        </div>

        <div className={`flex flex-wrap items-center gap-4 ${active ? '' : 'opacity-50 pointer-events-none'}`}>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="compareView"
              checked={compareViewMode === 'facet'}
              onChange={() => onChangeViewMode('facet')}
              className="w-4 h-4 border-2 border-slate-500 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 focus:ring-offset-[#1e293b] bg-[#0f172a]"
            />
            <span className="text-sm text-slate-300">Escenarios completos (facet)</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="compareView"
              checked={compareViewMode === 'by-year'}
              onChange={() => onChangeViewMode('by-year')}
              className="w-4 h-4 border-2 border-slate-500 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 focus:ring-offset-[#1e293b] bg-[#0f172a]"
            />
            <span className="text-sm text-slate-300">Por años seleccionados</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="compareView"
              checked={compareViewMode === 'line-total'}
              onChange={() => onChangeViewMode('line-total')}
              className="w-4 h-4 border-2 border-slate-500 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 focus:ring-offset-[#1e293b] bg-[#0f172a]"
            />
            <span className="text-sm text-slate-300">Líneas totales</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="radio"
              name="compareView"
              checked={compareViewMode === 'by-year-alt'}
              onChange={() => onChangeViewMode('by-year-alt')}
              className="w-4 h-4 border-2 border-slate-500 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 focus:ring-offset-[#1e293b] bg-[#0f172b]"
            />
            <span className="text-sm text-slate-300">Por años seleccionados - Alternativo</span>
          </label>
        </div>
      </div>

      {active && (compareViewMode === 'by-year' || compareViewMode === 'by-year-alt') && (
        <div className="bg-[#1e293b] p-4 rounded-xl border border-slate-700/50">
          <h3 className="text-sm font-bold text-slate-300 mb-3">
            {compareViewMode === 'by-year'
              ? 'Años a graficar (un grupo de barras por año)'
              : 'Años a graficar (barras dentro de cada escenario)'}
          </h3>
          <div className="flex flex-wrap gap-2 content-start">
            {AVAILABLE_YEARS.map((year) => {
              const isSelected = selectedYears.includes(year);
              return (
                <label
                  key={year}
                  className={`flex items-center justify-center px-3 py-1.5 rounded-full text-sm font-medium cursor-pointer transition-colors border select-none ${
                    isSelected
                      ? 'bg-blue-600/20 text-blue-400 border-blue-500/50'
                      : 'bg-[#0f172a] text-slate-400 border-slate-700 hover:border-slate-500'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => handleYearToggle(year)}
                    className="hidden"
                  />
                  {year}
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
