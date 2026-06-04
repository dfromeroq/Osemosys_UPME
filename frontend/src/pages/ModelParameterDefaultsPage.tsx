import { Navigate } from "react-router-dom";
import { paths } from "@/routes/paths";

/** Redirección legacy → pestaña Defaults del modelo en Catálogos. */
export function ModelParameterDefaultsPage() {
  return <Navigate to={`${paths.catalogs}?tab=model_defaults`} replace />;
}
