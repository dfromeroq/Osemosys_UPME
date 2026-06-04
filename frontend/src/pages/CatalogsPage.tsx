/**
 * CatalogsPage - CRUD de catálogos maestros y pestañas de configuración admin.
 *
 * Entidades: parámetros, regiones, tecnologías, combustibles, emisiones, solvers.
 * Configuración: defaults OSeMOSYS (model_defaults) e hilos globales del solver.
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { useToast } from "@/app/providers/useToast";
import { catalogsApi } from "@/features/catalogs/api/catalogsApi";
import {
  CATALOG_ENTITY_TABS,
  parseCatalogTabParam,
  visibleCatalogTabs,
  type CatalogPageTab,
} from "@/features/catalogs/catalogAccess";
import { ModelParameterDefaultsTab } from "@/features/catalogs/components/ModelParameterDefaultsTab";
import { SolverSettingsTab } from "@/features/catalogs/components/SolverSettingsTab";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { DataTable } from "@/shared/components/DataTable";
import { Modal } from "@/shared/components/Modal";
import { TextField } from "@/shared/components/TextField";
import type { CatalogEntity, CatalogItem } from "@/types/domain";

const entityLabel: Record<CatalogEntity, string> = {
  parameter: "Parámetros",
  region: "Regiones",
  technology: "Tecnologías",
  fuel: "Combustibles",
  emission: "Emisiones",
  solver: "Solvers",
};

const tabLabel: Record<CatalogPageTab, string> = {
  ...entityLabel,
  model_defaults: "Defaults del modelo",
  solver_config: "Config. solver",
};

function isCatalogEntity(tab: CatalogPageTab): tab is CatalogEntity {
  return (CATALOG_ENTITY_TABS as readonly string[]).includes(tab);
}

export function CatalogsPage() {
  const { user } = useCurrentUser();
  const { push } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const allowedTabs = useMemo(() => visibleCatalogTabs(user), [user]);
  const requestedTab = parseCatalogTabParam(searchParams.get("tab"));
  const activeTab: CatalogPageTab =
    requestedTab && allowedTabs.includes(requestedTab)
      ? requestedTab
      : (allowedTabs[0] ?? "parameter");

  const entity = isCatalogEntity(activeTab) ? activeTab : "parameter";
  const isEntityTab = isCatalogEntity(activeTab);

  const [showInactive, setShowInactive] = useState(true);
  const [rows, setRows] = useState<CatalogItem[]>([]);
  const [loadingRows, setLoadingRows] = useState(false);
  const [editing, setEditing] = useState<CatalogItem | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", justification: "" });

  const canManageCatalogs = Boolean(user?.can_manage_catalogs);
  const canManageModelDefaults = Boolean(user?.can_manage_model_defaults);
  const canManageSystemSettings = Boolean(user?.can_manage_system_settings);

  useEffect(() => {
    if (requestedTab && allowedTabs.includes(requestedTab)) return;
    if (allowedTabs.length === 0) return;
    const next = new URLSearchParams(searchParams);
    next.set("tab", allowedTabs[0]);
    setSearchParams(next, { replace: true });
  }, [allowedTabs, requestedTab, searchParams, setSearchParams]);

  function selectTab(tab: CatalogPageTab) {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next, { replace: true });
  }

  async function loadRows(nextEntity = entity, nextShowInactive = showInactive) {
    setLoadingRows(true);
    try {
      const data = await catalogsApi.list(nextEntity, { includeInactive: nextShowInactive });
      setRows(data);
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo cargar el catálogo.", "error");
      setRows([]);
    } finally {
      setLoadingRows(false);
    }
  }

  useEffect(() => {
    if (!isEntityTab) return;
    void loadRows(entity, showInactive);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity, showInactive, isEntityTab]);

  useEffect(() => {
    if (!isEntityTab) return;
    const handleFocus = () => {
      void loadRows(entity, showInactive);
    };
    const handleVisibility = () => {
      if (!document.hidden) {
        void loadRows(entity, showInactive);
      }
    };
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity, showInactive, isEntityTab]);

  const title = useMemo(
    () => (isEntityTab ? `Catálogo: ${entityLabel[entity]}` : tabLabel[activeTab]),
    [activeTab, entity, isEntityTab],
  );

  function openCreate() {
    setEditing(null);
    setForm({ name: "", justification: "" });
    setOpen(true);
  }

  function openEdit(item: CatalogItem) {
    setEditing(item);
    setForm({ name: item.name, justification: "" });
    setOpen(true);
  }

  async function save() {
    if (!canManageCatalogs) return;
    try {
      if (editing) {
        const justification = form.justification.trim();
        await catalogsApi.update(entity, editing.id, {
          name: form.name.trim(),
          ...(justification ? { justification } : {}),
        });
      } else {
        await catalogsApi.create({
          entity,
          name: form.name.trim(),
        });
      }
      await loadRows(entity, showInactive);
      setOpen(false);
      push("Catálogo guardado.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo guardar.", "error");
    }
  }

  async function toggleActive(item: CatalogItem) {
    if (!canManageCatalogs) return;
    const justification =
      window.prompt("Justificación (obligatoria si el registro ya está en uso):")?.trim() || undefined;
    await catalogsApi.deactivate(entity, item.id, justification);
    await loadRows(entity, showInactive);
    push("Registro desactivado.", "success");
  }

  if (allowedTabs.length === 0) {
    return (
      <section className="pageSection">
        <p>No tienes permisos para ver ninguna pestaña de catálogos.</p>
      </section>
    );
  }

  return (
    <section className="pageSection" style={{ display: "grid", gap: 14 }}>
      <div className="toolbarRow">
        <div>
          <h1 style={{ margin: 0 }}>Catálogos</h1>
          <p style={{ margin: "6px 0 0", opacity: 0.75 }}>
            Catálogos maestros y configuración global del modelo y del solver.
          </p>
        </div>
        {isEntityTab && canManageCatalogs ? (
          <Button variant="primary" onClick={openCreate}>
            Nuevo registro
          </Button>
        ) : isEntityTab ? (
          <Badge variant="neutral">Solo lectura (sin permiso de administración)</Badge>
        ) : null}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {allowedTabs.map((tab) => (
          <Button
            key={tab}
            variant={tab === activeTab ? "primary" : "ghost"}
            onClick={() => selectTab(tab)}
          >
            {tabLabel[tab]}
          </Button>
        ))}
      </div>

      {activeTab === "model_defaults" ? (
        <ModelParameterDefaultsTab canEdit={canManageModelDefaults} />
      ) : null}

      {activeTab === "solver_config" ? (
        <SolverSettingsTab canEdit={canManageSystemSettings} />
      ) : null}

      {isEntityTab ? (
        <>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Incluir desactivados
          </label>

          <DataTable
            rows={rows}
            rowKey={(r) => String(r.id)}
            columns={[
              { key: "id", header: "ID", render: (r) => r.id },
              { key: "name", header: "Nombre", render: (r) => r.name },
              {
                key: "active",
                header: "Estado",
                render: (r) => (
                  <Badge variant={r.is_active ? "success" : "danger"}>
                    {r.is_active ? "Activo" : "Inactivo"}
                  </Badge>
                ),
              },
              {
                key: "actions",
                header: "Acciones",
                render: (r) =>
                  canManageCatalogs ? (
                    <div style={{ display: "flex", gap: 8 }}>
                      <Button variant="ghost" onClick={() => openEdit(r)}>
                        Editar
                      </Button>
                      {r.is_active ? (
                        <Button variant="ghost" onClick={() => toggleActive(r)}>
                          Desactivar
                        </Button>
                      ) : null}
                    </div>
                  ) : (
                    <span style={{ opacity: 0.7 }}>Solo lectura</span>
                  ),
              },
            ]}
            searchableText={(r) => `${r.id} ${r.name}`}
          />
          {loadingRows ? <small style={{ opacity: 0.75 }}>Cargando catálogo...</small> : null}

          <Modal
            open={open}
            title={`${editing ? "Editar" : "Crear"} · ${title}`}
            onClose={() => setOpen(false)}
            footer={
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <Button variant="ghost" onClick={() => setOpen(false)}>
                  Cancelar
                </Button>
                <Button variant="primary" onClick={save} disabled={!canManageCatalogs}>
                  Guardar
                </Button>
              </div>
            }
          >
            <div style={{ display: "grid", gap: 10 }}>
              <TextField
                label="Nombre"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
              {editing ? (
                <TextField
                  label="Justificación (si está en uso, es obligatoria)"
                  value={form.justification}
                  onChange={(e) => setForm((p) => ({ ...p, justification: e.target.value }))}
                />
              ) : null}
            </div>
          </Modal>
        </>
      ) : null}
    </section>
  );
}
