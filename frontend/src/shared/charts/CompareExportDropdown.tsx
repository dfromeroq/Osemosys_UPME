import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, FileDown } from 'lucide-react';
import { Button } from '@/shared/components/Button';

export type CompareExportOption = {
  id: string;
  label: string;
  busyLabel?: string;
  onClick: () => Promise<void> | void;
  busy?: boolean;
};

type CompareExportDropdownProps = {
  disabled?: boolean;
  options: CompareExportOption[];
  className?: string;
};

export function CompareExportDropdown({
  disabled = false,
  options,
  className = '',
}: CompareExportDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const anyBusy = options.some((opt) => opt.busy);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  if (options.length === 0) return null;

  return (
    <div ref={ref} className={`relative ${className}`.trim()}>
      <Button
        type="button"
        variant="ghost"
        disabled={disabled || anyBusy}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-slate-600 hover:bg-slate-800/80 disabled:opacity-50"
      >
        <FileDown className="h-4 w-4 shrink-0" aria-hidden />
        {anyBusy ? 'Generando…' : 'Descargar'}
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
      </Button>
      {open ? (
        <div className="absolute right-0 top-full z-30 mt-1 min-w-[220px] rounded-lg border border-slate-800 bg-slate-900/95 p-1 shadow-2xl backdrop-blur-md">
          {options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              disabled={disabled || anyBusy}
              onClick={async () => {
                setOpen(false);
                await opt.onClick();
              }}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800/80 disabled:opacity-50"
            >
              <FileDown className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {opt.busy ? (opt.busyLabel ?? 'Generando…') : opt.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
