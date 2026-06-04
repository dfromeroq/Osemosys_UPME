import { Navigate } from "react-router-dom";
import { paths } from "@/routes/paths";

/** Redirección legacy → pestaña Config. solver en Catálogos. */
export function SystemSettingsAdminPage() {
  return <Navigate to={`${paths.catalogs}?tab=solver_config`} replace />;
}
