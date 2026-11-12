import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router";

import { read } from "../api/client";
import { useAuth, useMe } from "../auth/AuthContext";
import { accountOf, countUnsynchronized } from "../lib/hseOfflineSync";
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
    { to: "/plateforme/societes", text: "Sociétés clientes", show: can(me.grants, "organization.tenant.list") },
    { to: "/plateforme/nouvelle-societe", text: "Nouvelle société", show: can(me.grants, "organization.tenant.create") },
    { to: "/plateforme/plans", text: "Plans SaaS", show: can(me.grants, "billing.plan.list") },
    { to: "/plateforme/abonnements", text: "Abonnements", show: can(me.grants, "billing.subscription.manage") },
    { to: "/plateforme/facturation", text: "Facturation", show: can(me.grants, "billing.invoice.manage") },
    { to: "/plateforme/support", text: "Support société", show: can(me.grants, "organization.tenant.support") },
    { to: "/plateforme/etat", text: "État des services", show: can(me.grants, "organization.tenant.list") },
    { to: "/abonnement", text: "Abonnement", show: can(me.grants, "billing.subscription.read") },
    { to: "/demarrage", text: "Démarrage", show: can(me.grants, "organization.tenant.read") },
    { to: "/factures", text: "Factures", show: can(me.grants, "billing.invoice.read") },
    { to: "/vehicules", text: "Véhicules", show: can(me.grants, "fleet.vehicle.read") },
    { to: "/vehicules/echeances", text: "Échéances documents", show: can(me.grants, "fleet.document.read") },
    { to: "/flotte-gps", text: "Flotte GPS", show: can(me.grants, "fleet.vehicle.read") },
    { to: "/flotte-gps/zones", text: "Zones GPS", show: can(me.grants, "fleet.geofence.read") },
    { to: "/flotte-gps/alertes", text: "Alertes GPS", show: can(me.grants, "fleet.gps_alert.read") },
    { to: "/mon-suivi", text: "Mon partage GPS", show: can(me.grants, "fleet.gps.share") },
    { to: "/conducteurs", text: "Conducteurs", show: can(me.grants, "workforce.driver.read") },
    { to: "/affectations", text: "Affectations", show: can(me.grants, "assignment.vehicle_assignment.read") },
    { to: "/missions", text: "Missions", show: can(me.grants, "dispatch.mission.read") },
    { to: "/atelier", text: "Atelier", show: can(me.grants, "maintenance.work_order.read") },
    { to: "/atelier/fiabilite", text: "Fiabilité parc", show: can(me.grants, "maintenance.reliability.read") },
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
    { to: "/pneus", text: "Pneus", show: can(me.grants, "maintenance.tyre.read") },
    { to: "/pieces", text: "Pièces", show: can(me.grants, "maintenance.parts.read", siteId) },
    {
      to: "/hse",
      text: "Sécurité (HSE)",
      show:
        can(me.grants, "hse.incident.read") ||
        can(me.grants, "hse.incident.report") ||
        can(me.grants, "hse.inspection.perform"),
    },
    { to: "/hse/inspections", text: "Inspections HSE", show: can(me.grants, "hse.inspection.read") || can(me.grants, "hse.inspection.perform") },
    { to: "/hse/checklists", text: "Checklists HSE", show: can(me.grants, "hse.checklist.manage") },
    { to: "/pesees", text: "Pesées", show: can(me.grants, "dispatch.weighing.read") },
    { to: "/juridique", text: "Contrats & assurances", show: can(me.grants, "legal.contract.read", siteId) || can(me.grants, "legal.insurance.read", siteId) },
    { to: "/couts", text: "Coût complet", show: can(me.grants, "cost.vehicle.read") },
    { to: "/indicateurs", text: "Indicateurs", show: can(me.grants, "dispatch.indicators.read") },
    { to: "/administration", text: "Administration", show: canAdminister(me.grants) },
  ];
  // Associer l'icône au chemin, jamais à la position du lien : les permissions filtrent des entrées.
  const iconFor = (to: string): IconName => {
    if (to.startsWith("/plateforme") || to.startsWith("/administration")) return "settings";
    if (to.startsWith("/flotte-gps")) return "gps";
    if (to === "/mon-suivi") return "phone";
    if (to.startsWith("/vehicules")) return "truck";
    if (to.startsWith("/conducteurs")) return "users";
    if (to.startsWith("/affectations")) return "assignment";
    if (to.startsWith("/missions")) return "mission";
    if (to.startsWith("/atelier") || to.startsWith("/maintenance") || to.startsWith("/pieces") || to.startsWith("/pneus")) return "tool";
    if (to.startsWith("/carburant")) return "fuel";
    if (to.startsWith("/hse")) return "shield";
    if (to.startsWith("/pesees")) return "scale";
    if (to.startsWith("/indicateurs") || to.startsWith("/couts")) return "chart";
    return "calendar";
  };
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
          <Link to="/mon-compte/sessions">Mes sessions</Link>
          <button
            type="button"
            className="link"
            onClick={() => {
              setLogoutFailed(false);
              void (async () => {
                // La déconnexion volontaire efface la file locale : prévenir si des déclarations n'ont pas
                // encore été acquittées par le serveur.
                const unsent = await countUnsynchronized(accountOf(me)).catch(() => 0);
                if (
                  unsent > 0 &&
                  !window.confirm(
                    `${unsent} déclaration(s) saisie(s) sur cet appareil ne sont pas encore synchronisées et seront supprimées. Se déconnecter quand même ?`,
                  )
                ) {
                  return;
                }
                await logout();
              })().catch(() => setLogoutFailed(true));
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
                // Lien exact si une sous-page a son propre lien (Flotte GPS / Alertes GPS, Atelier / Fiabilité).
                <NavLink key={l.to} to={l.to} end={links.some((o) => o.to.startsWith(`${l.to}/`))} onClick={() => setMenuOpen(false)}>
                  <Icon name={iconFor(l.to)} />{l.text}
                </NavLink>
              ))}
            <div className="sidebar-footer"><span className="connection-dot" /> Exploitation minière<small>{me.workspace_code}</small></div>
          </nav>
          <main className="content">
            {me.is_demo && (
              <p className="demo-banner" role="note">
                Espace de démonstration : sociétés, personnes et opérations fictives ; les positions GPS peuvent être simulées.
              </p>
            )}
            <Outlet />
          </main>
        </>
      )}
    </div>
  );
}

