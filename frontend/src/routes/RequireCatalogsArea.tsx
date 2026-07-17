/**
 * Guard: acceso al área Catálogos (pestañas de entidades, defaults del modelo o config solver).
 */
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { canAccessCatalogsArea } from "@/features/catalogs/catalogAccess";
import { paths } from "@/routes/paths";

export function RequireCatalogsArea() {
  const { user, loading } = useCurrentUser();

  if (loading) return <section className="pageSection">Cargando permisos...</section>;
  if (!canAccessCatalogsArea(user)) {
    return <Navigate to={paths.scenarios} replace />;
  }
  return <Outlet />;
}
