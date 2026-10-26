import { NavLink, Outlet } from "react-router";

import { useAuth, useMe } from "../auth/AuthContext";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

export function Layout() {
  const me = useMe();
  const { logout } = useAuth();
  const { sites, siteId, setSiteId } = useSites();
  const links = [
    { to: "/vehicules", text: "Véhicules", show: can(me.grants, "fleet.vehicle.read") },
    { to: "/conducteurs", text: "Conducteurs", show: can(me.grants, "workforce.driver.read") },
    { to: "/affectations", text: "Affectations", show: can(me.grants, "assignment.vehicle_assignment.read") },
  ];
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <strong>MINEFLEET 360</strong>
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
        <div className="user">
          <span>{me.display_name}</span>
          <button type="button" className="link" onClick={() => void logout()}>
            Se déconnecter
          </button>
        </div>
      </header>
      <nav className="mainnav" aria-label="Navigation principale">
        <NavLink to="/" end>
          Accueil
        </NavLink>
        {links
          .filter((l) => l.show)
          .map((l) => (
            <NavLink key={l.to} to={l.to}>
              {l.text}
            </NavLink>
          ))}
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
