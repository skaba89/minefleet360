import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router";

import { read } from "../api/client";
import { useAuth, useMe } from "../auth/AuthContext";
import { can } from "../lib/permissions";
import { canAdminister } from "../pages/AdminPages";
import { SecurityPage } from "../pages/SecurityPage";
import { useSites } from "../site/SiteContext";
import { Icon, type IconName } from "./Icon";
import { ConnectivityStatus } from "./Connectivity";

export function Layout() {
  const me = useMe();
  const { logout } = useAuth();
  const { sites, siteId, setSiteId } = useSites();
  const [logoutFailed, setLogoutFailed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const canReadFuel = can(me.grants, "fuel.stock.read", siteId);
  const fuelAlerts = useQuery({
    queryKey: ["fuel-stock-alerts", siteId],
    enabled: canReadFuel,
    queryFn: () => read("/fuel/alerts", { query: { site_id: siteId, active_only: true, page: 1, page_size: 1 } }),
    refetchInterval: 60_000,
  });
  const links = [
    { to: "/vehicules", text: "Véhicules", show: can(me.grants, "fleet.vehicle.read") },
    { to: "/flotte-gps", text: "Flotte GPS", show: can(me.grants, "fleet.vehicle.read") },
    { to: "/mon-suivi", text: "Mon partage GPS", show: can(me.grants, "fleet.gps.share") },
    { to: "/conducteurs", text: "Conducteurs", show: can(me.grants, "workforce.driver.read") },
    { to: "/affectations", text: "Affectations", show: can(me.grants, "assignment.vehicle_assignment.read") },
    { to: "/missions", text: "Missions", show: can(me.grants, "dispatch.mission.read") },
    { to: "/atelier", text: "Atelier", show: can(me.grants, "maintenance.work_order.read") },
    { to: "/maintenance", text: "Maintenance", show: can(me.grants, "maintenance.preventive.read") },
    {
      to: "/carburant",
      text: "Carburant",
      show:
        can(me.grants, "fuel.stock.read") ||
        can(me.grants, "fuel.stock.manage") ||
        can(me.grants, "fuel.issue.request") ||
        can(me.grants, "fuel.stocktake.record") ||
        can(me.grants, "fuel.stock.threshold") ||
        can(me.grants, "fuel.purchase.read") ||
        can(me.grants, "fuel.purchase.create"),
    },
    { to: "/pieces", text: "Pièces", show: can(me.grants, "maintenance.parts.read", siteId) },
    { to: "/pesees", text: "Pesées", show: can(me.grants, "dispatch.weighing.read") },
    { to: "/indicateurs", text: "Indicateurs", show: can(me.grants, "dispatch.indicators.read") },
    { to: "/administration", text: "Administration", show: canAdminister(me.grants) },
  ];
  const icons: IconName[] = ["truck", "gps", "phone", "users", "assignment", "mission", "tool", "calendar", "fuel", "tool", "scale", "chart", "settings"];
  return (
    <div className={`shell${menuOpen ? " menu-open" : ""}`}>
      <header className="topbar">
        <button type="button" className="menu-toggle" aria-label="Afficher le menu" aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}><Icon name="menu" /></button>
        <div className="workspace-brand">
          <span className="muted">{me.tenant_display_name}</span>
        </div>
        <label className="site-picker">
          Site
          <select value={siteId ?? ""} onChange={(e) => setSiteId(e.target.value || null)}>
            <option value="">Tous mes sites</option>
            {sites.map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.code} — {s.name}
              </option>
            ))}
          </select>
        </label>
        <ConnectivityStatus />
        {canReadFuel && <Link className="notification-link" to="/carburant" aria-label={`${fuelAlerts.data?.total ?? 0} alerte(s) de stock carburant`}><Icon name="bell" />{(fuelAlerts.data?.total ?? 0) > 0 && <span>{fuelAlerts.data?.total}</span>}</Link>}
        <div className="user">
          <span className="user-avatar" aria-hidden="true">{me.display_name.slice(0, 1).toUpperCase()}</span>
          <span className="user-name">{me.display_name}<small>Mon espace</small></span>
          <Link to="/mon-compte/securite">Sécurité</Link>
          <button
            type="button"
            className="link"
            onClick={() => {
              setLogoutFailed(false);
              logout().catch(() => setLogoutFailed(true));
            }}
          >
            Se déconnecter
          </button>
        </div>
      </header>
      {logoutFailed && (
        <p className="error" role="alert">
          Déconnexion non confirmée par le serveur (réseau indisponible ?). Votre session reste ouverte :
          réessayez avant de quitter ce poste.
        </p>
      )}
      {me.mfa_enrollment_required ? (
        // Enrôlement doux (C-03) : seule la configuration du second facteur est accessible.
        <main className="content">
          <SecurityPage />
        </main>
      ) : (
        <>
          <nav id="main-navigation" className="mainnav" aria-label="Navigation principale">
            <Link to="/" className="sidebar-brand"><Icon name="shield" /><strong>MINEFLEET 360</strong></Link>
            <NavLink to="/" end>
              <Icon name="dashboard" /> Tableau de bord
            </NavLink>
            {links
              .filter((l) => l.show)
              .map((l) => (
                <NavLink key={l.to} to={l.to} onClick={() => setMenuOpen(false)}>
                  <Icon name={icons[links.indexOf(l)] ?? "dashboard"} />{l.text}
                </NavLink>
              ))}
            <div className="sidebar-footer"><span className="connection-dot" /> Exploitation minière<small>{me.workspace_code}</small></div>
          </nav>
          <main className="content">
            <Outlet />
          </main>
        </>
      )}
    </div>
  );
}

