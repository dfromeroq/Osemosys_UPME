/**
 * Guard de permisos: requiere can_manage_catalogs (p. ej. etiquetas de escenario).
 * La página Catálogos usa RequireCatalogsArea con permisos OR más amplios.
 */
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { paths } from "@/routes/paths";

export function RequireCatalogManager() {
  const { user, loading } = useCurrentUser();

  if (loading) return <section className="pageSection">Cargando permisos...</section>;
  if (!user?.can_manage_catalogs) {
    return <Navigate to={paths.scenarios} replace />;
  }
  return <Outlet />;
}

