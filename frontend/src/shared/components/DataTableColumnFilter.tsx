/**
 * Filtros por columna para DataTable: icono de embudo junto al encabezado + popover.
 * Multiselect reutiliza ColumnFilterPopover; text y select tienen popovers propios.
 */
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { ColumnFilterPopover } from "@/shared/components/ColumnFilterPopover";
import type { ColumnFilterConfig } from "@/shared/components/DataTable";

type Pos = { top: number; left: number };

type Props<T> = {
  columnLabel: string;
  config: ColumnFilterConfig<T>;
  multiOptions?: { value: string; label: string }[];
  textValue: string;
  multiSelected: string[];
  onTextChange: (value: string) => void;
  onMultiChange: (values: string[]) => void;
};

export function DataTableColumnFilter<T>({
  columnLabel,
  config,
  multiOptions = [],
  textValue,
  multiSelected,
  onTextChange,
  onMultiChange,
}: Props<T>) {
  if (config.type === "multiselect") {
    const labelByValue = new Map(multiOptions.map((o) => [o.value, o.label]));
    return (
      <ColumnFilterPopover
        columnLabel={columnLabel}
        options={multiOptions.map((o) => o.value)}
        selected={multiSelected}
        onChange={onMultiChange}
        renderOption={(value) =>
          labelByValue.get(value) ?? config.getLabel?.(value) ?? value
        }
      />
    );
  }

  if (config.type === "select") {
    return (
      <SelectColumnFilterPopover
        columnLabel={columnLabel}
        value={textValue}
        options={config.options ?? []}
        onChange={onTextChange}
      />
    );
  }

  return (
    <TextColumnFilterPopover
      columnLabel={columnLabel}
      value={textValue}
      placeholder={config.placeholder ?? "Filtrar…"}
      onChange={onTextChange}
    />
  );
}

function FilterIconButton({
  columnLabel,
  active,
  badge,
  onClick,
  btnRef,
}: {
  columnLabel: string;
  active: boolean;
  badge?: number | string;
  onClick: () => void;
  btnRef: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <button
      ref={btnRef}
      type="button"
      className={`col-filter-btn${active ? " col-filter-btn--active" : ""}`}
      aria-label={`Filtrar ${columnLabel}`}
      title={active ? `Filtro activo en ${columnLabel}` : `Filtrar ${columnLabel}`}
      onClick={onClick}
    >
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <polygon points="3 4 21 4 14 12.5 14 20 10 18 10 12.5 3 4" />
      </svg>
      {badge != null ? <span className="col-filter-badge">{badge}</span> : null}
    </button>
  );
}

function useFilterPopoverPosition(open: boolean, btnRef: RefObject<HTMLButtonElement | null>) {
  const [pos, setPos] = useState<Pos | null>(null);

  const computePos = () => {
    const el = btnRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const popoverWidth = 260;
    const margin = 8;
    let left = rect.left;
    const maxLeft = window.innerWidth - popoverWidth - margin;
    if (left > maxLeft) left = Math.max(margin, maxLeft);
    setPos({ top: rect.bottom + 4, left });
  };

  useLayoutEffect(() => {
    if (open) computePos();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => computePos();
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open]);

  return { pos, computePos };
}

function useCloseOnOutside(
  open: boolean,
  btnRef: RefObject<HTMLButtonElement | null>,
  popoverRef: RefObject<HTMLDivElement | null>,
  onClose: () => void,
) {
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (btnRef.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      onClose();
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        e.preventDefault();
        onClose();
        requestAnimationFrame(() => btnRef.current?.focus({ preventScroll: true }));
      }
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc, true);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc, true);
    };
  }, [open, btnRef, popoverRef, onClose]);
}

function TextColumnFilterPopover({
  columnLabel,
  value,
  placeholder,
  onChange,
}: {
  columnLabel: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const { pos } = useFilterPopoverPosition(open, btnRef);

  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  const close = () => setOpen(false);
  useCloseOnOutside(open, btnRef, popoverRef, close);

  const active = value.trim().length > 0;

  const apply = () => {
    onChange(draft.trim());
    close();
  };

  const clear = () => {
    setDraft("");
    onChange("");
    close();
  };

  return (
    <>
      <FilterIconButton
        columnLabel={columnLabel}
        active={active}
        onClick={() => setOpen((v) => !v)}
        btnRef={btnRef}
      />
      {open && pos
        ? createPortal(
            <div
              ref={popoverRef}
              className="col-filter-popover"
              role="dialog"
              aria-label={`Filtro ${columnLabel}`}
              style={{ top: pos.top, left: pos.left }}
            >
              <div className="col-filter-popover__head">
                <input
                  type="text"
                  className="col-filter-popover__search"
                  placeholder={placeholder}
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      apply();
                    }
                  }}
                />
              </div>
              <div className="col-filter-popover__actions">
                <button type="button" className="col-filter-popover__link" onClick={clear}>
                  Limpiar
                </button>
                <button type="button" className="col-filter-popover__link" onClick={apply}>
                  Aplicar
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function SelectColumnFilterPopover({
  columnLabel,
  value,
  options,
  onChange,
}: {
  columnLabel: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const { pos } = useFilterPopoverPosition(open, btnRef);

  const close = () => setOpen(false);
  useCloseOnOutside(open, btnRef, popoverRef, close);

  const active = value.length > 0;

  const pick = (next: string) => {
    onChange(next);
    close();
  };

  return (
    <>
      <FilterIconButton
        columnLabel={columnLabel}
        active={active}
        onClick={() => setOpen((v) => !v)}
        btnRef={btnRef}
      />
      {open && pos
        ? createPortal(
            <div
              ref={popoverRef}
              className="col-filter-popover"
              role="dialog"
              aria-label={`Filtro ${columnLabel}`}
              style={{ top: pos.top, left: pos.left }}
            >
              <div className="col-filter-popover__actions" style={{ justifyContent: "flex-start" }}>
                <button
                  type="button"
                  className="col-filter-popover__link"
                  onClick={() => pick("")}
                  disabled={!active}
                >
                  Todos
                </button>
              </div>
              <div className="col-filter-popover__list">
                {options.map((o) => {
                  const checked = value === o.value;
                  return (
                    <label key={o.value} className="col-filter-popover__item">
                      <input
                        type="radio"
                        name={`filter-${columnLabel}`}
                        checked={checked}
                        onChange={() => pick(o.value)}
                      />
                      <span>{o.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
