/**
 * Layout para páginas de autenticación (login).
 * Diseño split: aside con branding y capacidades del sistema, main con el formulario.
 */
import { Outlet } from "react-router-dom";
import logoUpme from "@/assets/logo_upme.png";

export function AuthLayout() {
  return (
    <div className="authLayout">
      <div className="authShell">
        <aside className="authAside" aria-hidden="true">
          <img className="authAside__logo" src={logoUpme} alt="UPME" />
          <p className="authAside__eyebrow">OSeMOSYS · ENERGY MODELLING WORKSPACE</p>
          <h2 className="authAside__title">Plataforma de escenarios energéticos</h2>
          <p className="authAside__text">
            Construye escenarios de planeación, ejecuta simulaciones con OSeMOSYS y analiza resultados
            para apoyar decisiones técnicas y regulatorias.
          </p>
          <div className="authCapabilities">
            <div className="authCapability">
              <h3>Diseño de escenarios</h3>
              <p>Configura supuestos de demanda, tecnologías, costos y restricciones.</p>
            </div>
            <div className="authCapability">
              <h3>Simulación y optimización</h3>
              <p>Integra OSeMOSYS para evaluar soluciones de mínimo costo y expansión.</p>
            </div>
            <div className="authCapability">
              <h3>Resultados accionables</h3>
              <p>Compara indicadores clave y soporta decisiones con evidencia cuantitativa.</p>
            </div>
          </div>
          <p className="authAside__footnote">Optimización costo-eficiente · Trazabilidad · Escalabilidad</p>
        </aside>

        <main className="authMain">
          <div className="authMainInner">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

