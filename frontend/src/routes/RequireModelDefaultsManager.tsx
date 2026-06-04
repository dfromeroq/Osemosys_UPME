import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "@/app/providers/useCurrentUser";
import { paths } from "@/routes/paths";

export function RequireModelDefaultsManager() {
  const { user, loading } = useCurrentUser();

  if (loading) {
    return <section className="pageSection">Cargando permisos...</section>;
  }
  if (!user?.can_manage_model_defaults) {
    return <Navigate to={paths.scenarios} replace />;
  }
  return <Outlet />;
}
