/**
 * Configuración del router con lazy loading de páginas.
 * Rutas públicas: login. Rutas protegidas: /app/* con RequireAuth.
 * Guards anidados: RequireUserManager, RequireCatalogManager, RequireOfficialDataImporter.
 */
/* eslint-disable react-refresh/only-export-components -- helpers locales (Suspense, rutas) junto al router */
import { lazy, Suspense } from "react";
import { Navigate, Outlet, createBrowserRouter, useParams } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthLayout } from "@/layouts/AuthLayout";
import { RequireAuth } from "@/routes/RequireAuth";
import { RequireCatalogManager } from "@/routes/RequireCatalogManager";
import { RequireOfficialDataImporter } from "@/routes/RequireOfficialDataImporter";
import { RequireSystemSettingsManager } from "@/routes/RequireSystemSettingsManager";
import { RequireUserManager } from "@/routes/RequireUserManager";
import { paths } from "@/routes/paths";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RouteErrorPage } from "@/pages/RouteErrorPage";

const HomePage = lazy(() => import("@/pages/HomePage").then((m) => ({ default: m.HomePage })));
const ScenariosPage = lazy(() => import("@/pages/ScenariosPage").then((m) => ({ default: m.ScenariosPage })));
const ScenarioDetailPage = lazy(() => import("@/pages/ScenarioDetailPage").then((m) => ({ default: m.ScenarioDetailPage })));
const CatalogsPage = lazy(() => import("@/pages/CatalogsPage").then((m) => ({ default: m.CatalogsPage })));
const SimulationPage = lazy(() => import("@/pages/SimulationPage").then((m) => ({ default: m.SimulationPage })));
const ResultsPage = lazy(() => import("@/pages/ResultsPage").then((m) => ({ default: m.ResultsPage })));
const ResultDetailPage = lazy(() => import("@/pages/ResultDetailPage").then((m) => ({ default: m.ResultDetailPage })));
const ResultDataExplorerPage = lazy(() => import("@/pages/ResultDataExplorerPage").then((m) => ({ default: m.ResultDataExplorerPage })));
const InfeasibilityReportPage = lazy(() => import("@/pages/InfeasibilityReportPage").then((m) => ({ default: m.InfeasibilityReportPage })));
const ChangeRequestsPage = lazy(() => import("@/pages/ChangeRequestsPage").then((m) => ({ default: m.ChangeRequestsPage })));
const OfficialImportPage = lazy(() => import("@/pages/OfficialImportPage").then((m) => ({ default: m.OfficialImportPage })));
const UsersAdminPage = lazy(() => import("@/pages/UsersAdminPage").then((m) => ({ default: m.UsersAdminPage })));
const ProfilePage = lazy(() => import("@/pages/ProfilePage").then((m) => ({ default: m.ProfilePage })));
const ReportsPage = lazy(() => import("@/pages/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const ReportDashboardPage = lazy(() => import("@/pages/ReportDashboardPage").then((m) => ({ default: m.ReportDashboardPage })));
const HistoryPage = lazy(() => import("@/pages/HistoryPage").then((m) => ({ default: m.HistoryPage })));
const ScenarioTagsAdminPage = lazy(() => import("@/pages/ScenarioTagsAdminPage").then((m) => ({ default: m.ScenarioTagsAdminPage })));
const SystemSettingsAdminPage = lazy(() => import("@/pages/SystemSettingsAdminPage").then((m) => ({ default: m.SystemSettingsAdminPage })));
const ChartViewerPage = lazy(() => import("@/pages/ChartViewerPage").then((m) => ({ default: m.ChartViewerPage })));

/** Placeholder mínimo mientras se carga una página lazy (sin artefactos visuales). */
function LazyFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        padding: 24,
        opacity: 0.6,
        fontSize: 13,
      }}
    >
      Cargando…
    </div>
  );
}

/** Envuelve rutas lazy con Suspense para mostrar LazyFallback durante la carga */
function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LazyFallback />}>{children}</Suspense>;
}

/**
 * Wrapper para ResultDetailPage que usa `key={runId}` para forzar un remount
 * completo cada vez que el run cambia. Sin esto, React reutiliza la misma
 * instancia del componente al navegar entre distintos runIds (mismo patrón de
 * ruta), conservando estado obsoleto y mostrando datos del run anterior.
 */
function ResultDetailRoute() {
  const { runId } = useParams<{ runId: string }>();
  return <ResultDetailPage key={runId} />;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Outlet />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <Navigate to={paths.login} replace /> },
      {
        element: <AuthLayout />,
        children: [{ path: paths.login, element: <LoginPage /> }],
      },
      {
        element: <RequireAuth />,
        children: [
          {
            // Visor amplificado fuera de AppLayout (sin sidebar de
            // navegación). Vive en /app/charts/viewer/:jobId.
            path: "/app/charts/viewer/:jobId",
            element: <SuspenseWrapper><ChartViewerPage /></SuspenseWrapper>,
          },
          {
            path: paths.app,
            element: <AppLayout />,
            children: [
              { index: true, element: <SuspenseWrapper><HomePage /></SuspenseWrapper> },
              { path: "scenarios", element: <SuspenseWrapper><ScenariosPage /></SuspenseWrapper> },
              { path: "scenarios/:id", element: <SuspenseWrapper><ScenarioDetailPage /></SuspenseWrapper> },
              { path: "change-requests", element: <SuspenseWrapper><ChangeRequestsPage /></SuspenseWrapper> },
              { path: "simulation", element: <SuspenseWrapper><SimulationPage /></SuspenseWrapper> },
              { path: "results", element: <SuspenseWrapper><ResultsPage /></SuspenseWrapper> },
              { path: "results/:runId", element: <SuspenseWrapper><ResultDetailRoute /></SuspenseWrapper> },
              { path: "results/:runId/data", element: <SuspenseWrapper><ResultDataExplorerPage /></SuspenseWrapper> },
              { path: "reports", element: <SuspenseWrapper><ReportsPage /></SuspenseWrapper> },
              { path: "history", element: <SuspenseWrapper><HistoryPage /></SuspenseWrapper> },
              { path: "reports/:reportId", element: <SuspenseWrapper><ReportDashboardPage /></SuspenseWrapper> },
              { path: "simulations/:runId/infeasibility", element: <SuspenseWrapper><InfeasibilityReportPage /></SuspenseWrapper> },
              { path: "profile", element: <SuspenseWrapper><ProfilePage /></SuspenseWrapper> },
              {
                element: <RequireUserManager />,
                children: [{ path: "users-admin", element: <SuspenseWrapper><UsersAdminPage /></SuspenseWrapper> }],
              },
              {
                element: <RequireSystemSettingsManager />,
                children: [{ path: "system-settings", element: <SuspenseWrapper><SystemSettingsAdminPage /></SuspenseWrapper> }],
              },
              {
                element: <RequireCatalogManager />,
                children: [
                  { path: "catalogs", element: <SuspenseWrapper><CatalogsPage /></SuspenseWrapper> },
                  { path: "scenario-tags-admin", element: <SuspenseWrapper><ScenarioTagsAdminPage /></SuspenseWrapper> },
                ],
              },
              {
                element: <RequireOfficialDataImporter />,
                children: [{ path: "official-import", element: <SuspenseWrapper><OfficialImportPage /></SuspenseWrapper> }],
              },
            ],
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

