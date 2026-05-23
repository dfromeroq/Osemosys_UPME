/**
 * Layout principal de la aplicación autenticada.
 * Sidebar colapsable (estado persistido en localStorage). Cuando está
 * colapsado, queda totalmente oculto y un botón flotante en el header
 * permite restaurarlo. Cuando está expandido, el botón vive en el sidebar.
 */
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { paths } from "@/routes/paths";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { Button } from "@/shared/components/Button";
import { useCurrentUser } from "@/app/providers/useCurrentUser";

const SIDEBAR_KEY = "app.sidebar.collapsed";

function loadSidebarCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(SIDEBAR_KEY) === "1";
}

export function AppLayout() {
  const { logout } = useAuth();
  const { user } = useCurrentUser();
  const [collapsed, setCollapsed] = useState<boolean>(() =>
    loadSidebarCollapsed(),
  );

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  // Permite que cualquier página dispare ``app:collapse-sidebar`` para
  // forzar el colapso del menú lateral. Caso de uso: links compartibles a
  // gráficas, donde queremos maximizar el área de visualización.
  useEffect(() => {
    const handler = () => setCollapsed(true);
    window.addEventListener("app:collapse-sidebar", handler);
    return () => window.removeEventListener("app:collapse-sidebar", handler);
  }, []);

  const navItems = [
    { to: paths.app, label: "Inicio" },
    { to: paths.scenarios, label: "Escenarios" },
    { to: paths.changeRequests, label: "Solicitudes de cambio" },
    ...(user?.can_manage_catalogs ? [{ to: paths.catalogs, label: "Catálogos" }] : []),
    ...(user?.can_manage_users ? [{ to: paths.usersAdmin, label: "Usuarios y permisos" }] : []),
    ...(user?.can_manage_system_settings ? [{ to: paths.systemSettingsAdmin, label: "Configuración" }] : []),
    { to: paths.simulation, label: "Simulación" },
    { to: paths.results, label: "Resultados" },
    { to: paths.reports, label: "Reportes" },
    { to: paths.history, label: "Historial" },
    { to: paths.profile, label: "Perfil" },
  ];

  return (
    <div className="appShell" data-sidebar-collapsed={collapsed ? "true" : "false"}>
      {!collapsed ? (
        <aside className="appSidebar">
          <div
            style={{
              padding: "18px 16px 10px",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
              flexShrink: 0,
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: 8,
            }}
          >
            <div>
              <h2 style={{ margin: 0, fontSize: 17 }}>OSeMOSYS UI</h2>
              <p style={{ margin: "6px 0 0", fontSize: 12, opacity: 0.75 }}>
                Planeación y simulación energética
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              title="Ocultar barra lateral"
              aria-label="Ocultar barra lateral"
              style={{
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "#cbd5e1",
                width: 28,
                height: 28,
                borderRadius: 6,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 14,
                lineHeight: 1,
                flexShrink: 0,
              }}
            >
              «
            </button>
          </div>
          <nav className="appSidebarNav">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === paths.app}
                className={({ isActive }) =>
                  isActive ? "sidebarLink sidebarLink--active" : "sidebarLink"
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
      ) : null}

      <section style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
        <header
          className="appTopHeader"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px",
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            background: "rgb(11, 18, 32)",
            position: "sticky",
            top: 0,
            zIndex: 100,
            boxShadow: "0 1px 0 rgba(0, 0, 0, 0.35)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            {collapsed ? (
              <button
                type="button"
                onClick={() => setCollapsed(false)}
                title="Mostrar barra lateral"
                aria-label="Mostrar barra lateral"
                style={{
                  background: "rgba(34,211,238,0.12)",
                  border: "1px solid rgba(34,211,238,0.4)",
                  color: "#67e8f9",
                  height: 36,
                  padding: "0 12px",
                  borderRadius: 8,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  flexShrink: 0,
                }}
              >
                ☰ <span>Menú</span>
              </button>
            ) : null}
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700 }}>Sistema de escenarios OSeMOSYS</div>
              <small style={{ opacity: 0.75 }}>
                {user ? `${user.username} · ${user.email}` : "Sin sesión"}
              </small>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Button variant="ghost" onClick={logout}>
              Cerrar sesión
            </Button>
          </div>
        </header>

        <main className="appMainOutlet" style={{ padding: 20 }}>
          <Outlet />
        </main>
      </section>
    </div>
  );
}
