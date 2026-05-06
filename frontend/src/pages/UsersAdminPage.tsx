/**
 * UsersAdminPage - Administración de usuarios y permisos
 *
 * UX:
 *   - Banner con la leyenda de roles (qué habilita cada flag).
 *   - Cada usuario muestra sus permisos como chips informativos (no clicables).
 *   - Al hacer clic en "Editar" el usuario entra en modo edición: los chips se
 *     vuelven toggles; nada se persiste hasta pulsar "Guardar cambios".
 *   - Confirmaciones para acciones peligrosas: desactivarse a sí mismo o
 *     quitarse el permiso de administración de usuarios.
 *   - "Resetear contraseña" para forzar una nueva clave conocida.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@/app/providers/useToast";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { usersApi } from "@/features/users/api/usersApi";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { DataTable } from "@/shared/components/DataTable";
import { Modal } from "@/shared/components/Modal";
import { TextField } from "@/shared/components/TextField";
import type { User } from "@/types/domain";

type PermKey =
  | "is_active"
  | "can_manage_catalogs"
  | "can_import_official_data"
  | "can_manage_users"
  | "can_manage_scenarios"
  | "is_admin_reports"
  | "can_manage_system_settings";

type PermState = Record<PermKey, boolean>;

const PERMS: {
  key: PermKey;
  label: string;
  badge: string;
  description: string;
}[] = [
  {
    key: "is_active",
    label: "Activo",
    badge: "Activo",
    description:
      "El usuario puede iniciar sesión. Si lo desactivas no podrá entrar a la app.",
  },
  {
    key: "can_manage_scenarios",
    label: "Admin Escenarios",
    badge: "Admin escenarios",
    description:
      "Administra integralmente escenarios de otros usuarios: ve privados, edita metadatos, política, etiquetas y valores; administra permisos granulares; clona, exporta y revisa change requests; elimina escenarios y simulaciones/resultados ajenos. Úsalo con cuidado — las eliminaciones son permanentes (quedan registradas en Historial).",
  },
  {
    key: "can_manage_users",
    label: "Administrar usuarios",
    badge: "Admin usuarios",
    description:
      "Puede ver esta página, crear usuarios y otorgar/revocar permisos (incluido el de administrador).",
  },
  {
    key: "is_admin_reports",
    label: "Admin Reportes",
    badge: "Admin Reportes",
    description:
      "Puede marcar/desmarcar reportes como oficiales, editar reportes oficiales, cambiar el nombre de reportes públicos ajenos y ver reportes privados de otros usuarios (solo lectura).",
  },
  {
    key: "can_manage_catalogs",
    label: "Gestionar catálogos",
    badge: "Catálogos",
    description:
      "Puede editar parámetros, tecnologías y etiquetas del modelo.",
  },
  {
    key: "can_import_official_data",
    label: "Carga oficial",
    badge: "Carga oficial",
    description:
      "Puede subir archivos Excel/XLSM como datos oficiales del modelo (reemplaza la BD).",
  },
  {
    key: "can_manage_system_settings",
    label: "Admin Configuración",
    badge: "Config sistema",
    description:
      "Puede modificar la configuración runtime del sistema (ej. número de hilos del solver) desde el panel admin.",
  },
];

function permStateFrom(u: User): PermState {
  return {
    is_active: u.is_active,
    can_manage_catalogs: u.can_manage_catalogs,
    can_import_official_data: u.can_import_official_data,
    can_manage_users: u.can_manage_users,
    can_manage_scenarios: u.can_manage_scenarios ?? false,
    is_admin_reports: u.is_admin_reports ?? false,
    can_manage_system_settings: u.can_manage_system_settings ?? false,
  };
}

function somethingChanged(a: PermState, b: PermState): boolean {
  return (Object.keys(a) as PermKey[]).some((k) => a[k] !== b[k]);
}

export function UsersAdminPage() {
  const { push } = useToast();
  const { user: currentUser } = useCurrentUser();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [openCreate, setOpenCreate] = useState(false);

  /** Fila en edición y sus permisos pendientes (no persistidos aún). */
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PermState | null>(null);
  const [saving, setSaving] = useState(false);

  /** Reset de contraseña por usuario. */
  const [resetPwId, setResetPwId] = useState<string | null>(null);
  const [resetPwValue, setResetPwValue] = useState("");
  const [resetPwSaving, setResetPwSaving] = useState(false);

  const [form, setForm] = useState({
    email: "",
    username: "",
    password: "",
    is_active: true,
    can_manage_catalogs: false,
    can_import_official_data: false,
    can_manage_users: false,
    can_manage_scenarios: false,
    is_admin_reports: false,
    can_manage_system_settings: false,
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await usersApi.listUsers());
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo cargar usuarios.", "error");
    } finally {
      setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function createUser() {
    if (!form.email.trim() || !form.username.trim() || !form.password.trim()) {
      push("Email, usuario y contraseña son obligatorios.", "error");
      return;
    }
    try {
      await usersApi.createUser({
        email: form.email.trim(),
        username: form.username.trim(),
        password: form.password,
        is_active: form.is_active,
        can_manage_catalogs: form.can_manage_catalogs,
        can_import_official_data: form.can_import_official_data,
        can_manage_users: form.can_manage_users,
        can_manage_scenarios: form.can_manage_scenarios,
        is_admin_reports: form.is_admin_reports,
        can_manage_system_settings: form.can_manage_system_settings,
      });
      setOpenCreate(false);
      setForm({
        email: "",
        username: "",
        password: "",
        is_active: true,
        can_manage_catalogs: false,
        can_import_official_data: false,
        can_manage_users: false,
        can_manage_scenarios: false,
        is_admin_reports: false,
        can_manage_system_settings: false,
      });
      await refresh();
      push("Usuario creado.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "No se pudo crear usuario.", "error");
    }
  }

  function startEdit(u: User) {
    setEditingId(u.id);
    setDraft(permStateFrom(u));
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft(null);
  }

  async function saveEdit(u: User) {
    if (!draft) return;
    const original = permStateFrom(u);
    if (!somethingChanged(original, draft)) {
      cancelEdit();
      return;
    }
    // Salvaguardas: evitar bloquearse uno mismo.
    const isSelf = currentUser?.id === u.id;
    if (isSelf) {
      if (original.is_active && !draft.is_active) {
        if (
          !confirm(
            "Estás a punto de DESACTIVAR tu propio usuario. Te cerrará sesión y nadie podrá reactivarlo a menos que otro admin esté disponible. ¿Continuar?",
          )
        ) {
          return;
        }
      }
      if (original.can_manage_users && !draft.can_manage_users) {
        if (
          !confirm(
            "Estás a punto de QUITARTE a ti mismo el permiso 'Administrar usuarios'. No podrás volver a entrar a esta página. ¿Continuar?",
          )
        ) {
          return;
        }
      }
    }
    // Si queda sin admins con este cambio, advertir.
    const adminsAfter = users.reduce((acc, other) => {
      const s = other.id === u.id ? draft : permStateFrom(other);
      return acc + (s.is_active && s.can_manage_users ? 1 : 0);
    }, 0);
    if (adminsAfter === 0) {
      if (
        !confirm(
          "Con este cambio no quedará ningún usuario administrador activo. ¿Continuar?",
        )
      ) {
        return;
      }
    }

    setSaving(true);
    try {
      const updated = await usersApi.setPermissions(u.id, draft);
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      push("Permisos actualizados.", "success");
      cancelEdit();
    } catch (err) {
      push(
        err instanceof Error ? err.message : "No se pudieron actualizar permisos.",
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  async function resetPassword() {
    if (!resetPwId) return;
    if (resetPwValue.length < 6) {
      push("La contraseña debe tener al menos 6 caracteres.", "error");
      return;
    }
    setResetPwSaving(true);
    try {
      await usersApi.resetPassword(resetPwId, resetPwValue);
      push("Contraseña restablecida.", "success");
      setResetPwId(null);
      setResetPwValue("");
    } catch (err) {
      push(
        err instanceof Error ? err.message : "No se pudo restablecer la contraseña.",
        "error",
      );
    } finally {
      setResetPwSaving(false);
    }
  }

  const adminCount = useMemo(
    () => users.filter((u) => u.is_active && u.can_manage_users).length,
    [users],
  );

  return (
    <section className="pageSection" style={{ display: "grid", gap: 14 }}>
      <div className="toolbarRow">
        <div>
          <h1 style={{ margin: 0 }}>Usuarios y permisos</h1>
          <small style={{ opacity: 0.75 }}>
            {users.length} usuario{users.length === 1 ? "" : "s"} ·{" "}
            <strong>{adminCount}</strong> administrador{adminCount === 1 ? "" : "es"} activo
            {adminCount === 1 ? "" : "s"}
          </small>
        </div>
        <Button variant="primary" onClick={() => setOpenCreate(true)}>
          Crear usuario
        </Button>
      </div>

      {/* Leyenda explicativa */}
      <div
        style={{
          border: "1px solid rgba(59,130,246,0.25)",
          background: "rgba(59,130,246,0.06)",
          borderRadius: 12,
          padding: 14,
          display: "grid",
          gap: 8,
          color: "#cbd5e1",
        }}
      >
        <strong style={{ color: "#93c5fd" }}>Qué significa cada permiso</strong>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 10,
          }}
        >
          {PERMS.map((p) => (
            <div key={p.key}>
              <div style={{ fontWeight: 600, fontSize: 13, color: "#e2e8f0" }}>
                {p.label}
              </div>
              <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>
                {p.description}
              </div>
            </div>
          ))}
        </div>
        <small style={{ opacity: 0.75 }}>
          Para marcar reportes como <strong>Oficiales</strong> el usuario debe
          tener activo el permiso <strong>Gestionar catálogos</strong>. Para un
          administrador completo, habilita los 4 permisos.
        </small>
      </div>

      {loading ? <p>Cargando usuarios...</p> : null}

      <DataTable
        rows={users}
        rowKey={(r) => r.id}
        columns={[
          {
            key: "username",
            header: "Usuario",
            render: (r) => (
              <div style={{ display: "grid", gap: 2 }}>
                <span style={{ fontWeight: 600 }}>
                  {r.username}
                  {currentUser?.id === r.id ? (
                    <span
                      style={{
                        marginLeft: 6,
                        fontSize: 10,
                        padding: "1px 6px",
                        borderRadius: 999,
                        border: "1px solid rgba(16,185,129,0.4)",
                        background: "rgba(16,185,129,0.1)",
                        color: "#6ee7b7",
                      }}
                    >
                      TÚ
                    </span>
                  ) : null}
                </span>
                <small style={{ opacity: 0.7 }}>{r.email}</small>
              </div>
            ),
            filter: {
              type: "text",
              getValue: (r) => `${r.username} ${r.email}`,
              placeholder: "Usuario/email…",
            },
          },
          {
            key: "perms",
            header: "Permisos",
            render: (r) => {
              const isEditing = editingId === r.id;
              const state = isEditing && draft ? draft : permStateFrom(r);
              return (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {PERMS.map((p) => {
                    const on = state[p.key];
                    if (!isEditing) {
                      return (
                        <Badge
                          key={p.key}
                          variant={
                            p.key === "is_active"
                              ? on
                                ? "success"
                                : "danger"
                              : on
                                ? "success"
                                : "neutral"
                          }
                        >
                          {on ? `✓ ${p.badge}` : `· ${p.badge}`}
                        </Badge>
                      );
                    }
                    return (
                      <label
                        key={p.key}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                          padding: "4px 8px",
                          borderRadius: 999,
                          border: on
                            ? "1px solid rgba(16,185,129,0.45)"
                            : "1px solid rgba(255,255,255,0.12)",
                          background: on
                            ? "rgba(16,185,129,0.12)"
                            : "rgba(255,255,255,0.03)",
                          cursor: "pointer",
                          fontSize: 12,
                        }}
                        title={p.description}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={(e) =>
                            setDraft((prev) =>
                              prev ? { ...prev, [p.key]: e.target.checked } : prev,
                            )
                          }
                        />
                        {p.badge}
                      </label>
                    );
                  })}
                </div>
              );
            },
            filter: {
              type: "select",
              getValue: (r) => {
                const s = permStateFrom(r);
                return s.is_active && s.can_manage_users
                  ? "admin"
                  : !s.is_active
                    ? "inactive"
                    : "user";
              },
              options: [
                { value: "admin", label: "Administradores activos" },
                { value: "user", label: "Usuarios activos (sin admin)" },
                { value: "inactive", label: "Inactivos" },
              ],
            },
          },
          {
            key: "actions",
            header: "Acciones",
            render: (r) => {
              const isEditing = editingId === r.id;
              if (isEditing) {
                const changed =
                  draft !== null && somethingChanged(permStateFrom(r), draft);
                return (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <Button
                      variant="primary"
                      onClick={() => void saveEdit(r)}
                      disabled={!changed || saving}
                    >
                      {saving ? "Guardando…" : "Guardar cambios"}
                    </Button>
                    <Button variant="ghost" onClick={cancelEdit} disabled={saving}>
                      Cancelar
                    </Button>
                  </div>
                );
              }
              return (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <Button variant="ghost" onClick={() => startEdit(r)}>
                    Editar
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setResetPwId(r.id);
                      setResetPwValue("");
                    }}
                  >
                    Contraseña
                  </Button>
                </div>
              );
            },
          },
        ]}
        searchableText={(r) => `${r.username} ${r.email}`}
      />

      {/* Modal: crear usuario */}
      <Modal
        open={openCreate}
        title="Crear usuario"
        onClose={() => setOpenCreate(false)}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button variant="ghost" onClick={() => setOpenCreate(false)}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={() => void createUser()}>
              Guardar
            </Button>
          </div>
        }
      >
        <div style={{ display: "grid", gap: 12 }}>
          <TextField
            label="Email"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
          />
          <TextField
            label="Usuario"
            value={form.username}
            onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))}
          />
          <TextField
            label="Contraseña"
            type="password"
            value={form.password}
            onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
          />
          <div
            style={{
              display: "grid",
              gap: 6,
              padding: 10,
              borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <strong style={{ fontSize: 12, color: "#cbd5e1" }}>
              Permisos iniciales
            </strong>
            {PERMS.map((p) => {
              const k = p.key;
              const value = form[k];
              return (
                <label
                  key={p.key}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 8,
                    fontSize: 13,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={value}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, [k]: e.target.checked }))
                    }
                    style={{ marginTop: 3 }}
                  />
                  <span>
                    <strong>{p.label}</strong>
                    <br />
                    <small style={{ opacity: 0.75 }}>{p.description}</small>
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      </Modal>

      {/* Modal: resetear contraseña */}
      <Modal
        open={resetPwId !== null}
        title="Restablecer contraseña"
        onClose={() => {
          setResetPwId(null);
          setResetPwValue("");
        }}
        footer={
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button
              variant="ghost"
              disabled={resetPwSaving}
              onClick={() => {
                setResetPwId(null);
                setResetPwValue("");
              }}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              disabled={resetPwSaving || resetPwValue.length < 6}
              onClick={() => void resetPassword()}
            >
              {resetPwSaving ? "Guardando…" : "Restablecer"}
            </Button>
          </div>
        }
      >
        <div style={{ display: "grid", gap: 10 }}>
          <p style={{ margin: 0, fontSize: 13 }}>
            Asigna una nueva contraseña temporal. Compártela con el usuario por un
            canal seguro y pídele que la cambie al entrar.
          </p>
          <TextField
            label="Nueva contraseña (mín. 6 caracteres)"
            type="password"
            value={resetPwValue}
            onChange={(e) => setResetPwValue(e.target.value)}
          />
        </div>
      </Modal>
    </section>
  );
}
