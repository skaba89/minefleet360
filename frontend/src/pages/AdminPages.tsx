import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Navigate, NavLink, Outlet } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import { ActionForm, Options, orNull } from "../components/forms";
import { label } from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";
import { PHONE_PATTERN } from "./DriversPage";

const SITE_TYPES: Record<string, string> = {
  MINE: "Mine",
  QUARRY: "Carrière",
  WORKSHOP: "Atelier",
  DEPOT: "Dépôt",
  PORT: "Port",
  OFFICE: "Bureau",
};
const USER_STATUS: Record<string, string> = { INVITED: "Invité", ACTIVE: "Actif", DISABLED: "Désactivé" };
const SCOPES: Record<string, string> = { TENANT: "Toute la société", SITE: "Un site" };
// Fuseaux proposés pour un site (IANA) ; le serveur valide tout fuseau IANA.
const TIMEZONES = ["Africa/Conakry", "Africa/Abidjan", "Africa/Dakar", "Africa/Bamako", "Africa/Lagos", "Europe/Paris"];

/** Premier onglet accessible (l'administration n'est montrée qu'aux rôles qui en ont au moins un). */
export function AdminIndex() {
  const me = useMe();
  const target = can(me.grants, "organization.site.create")
    ? "sites"
    : can(me.grants, "identity.user.read")
      ? "utilisateurs"
      : can(me.grants, "audit.event.read")
        ? "journal"
        : "lieux-matieres";
  return <Navigate to={target} replace />;
}

function Denied() {
  return (
    <p className="error" role="alert">
      Vous n'avez pas accès à cette partie de l'administration.
    </p>
  );
}

export function AdminLayout() {
  const me = useMe();
  if (!canAdminister(me.grants)) return <Denied />;
  const tabs = [
    { to: "sites", text: "Sites", show: can(me.grants, "organization.site.create") },
    {
      to: "lieux-matieres",
      text: "Lieux et matières",
      show: can(me.grants, "dispatch.location.manage") || can(me.grants, "dispatch.material.manage"),
    },
    { to: "utilisateurs", text: "Utilisateurs et rôles", show: can(me.grants, "identity.user.read") },
    { to: "journal", text: "Journal d'audit", show: can(me.grants, "audit.event.read") },
  ];
  return (
    <section>
      <h1>Administration</h1>
      <nav className="tabs" aria-label="Administration">
        {tabs
          .filter((t) => t.show)
          .map((t) => (
            <NavLink key={t.to} to={t.to}>
              {t.text}
            </NavLink>
          ))}
      </nav>
      <Outlet />
    </section>
  );
}

export function canAdminister(grants: Schemas["GrantOut"][]): boolean {
  return (
    can(grants, "organization.site.create") ||
    can(grants, "identity.user.read") ||
    can(grants, "audit.event.read") ||
    can(grants, "dispatch.location.manage") ||
    can(grants, "dispatch.material.manage")
  );
}

// --- Sites ---------------------------------------------------------------------------------------------

type Site = Schemas["SiteOut"];

export function SitesAdminPage() {
  const me = useMe();
  if (!can(me.grants, "organization.site.create")) return <Denied />;
  return <SitesAdmin />;
}

function SitesAdmin() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Site | null>(null);
  const sites = useQuery({ queryKey: ["admin-sites"], queryFn: () => read("/sites", { query: { page_size: 200 } }) });
  const refresh = () => {
    setCreating(false);
    setEditing(null);
    void queryClient.invalidateQueries({ queryKey: ["admin-sites"] });
    void queryClient.invalidateQueries({ queryKey: ["sites"] });
  };
  const items = sites.data?.items ?? [];
  return (
    <>
      {!creating && (
        <button type="button" className="primary" onClick={() => setCreating(true)}>
          Nouveau site
        </button>
      )}
      {creating && <SiteForm onDone={refresh} onCancel={() => setCreating(false)} />}
      {editing && <SiteForm site={editing} onDone={refresh} onCancel={() => setEditing(null)} />}
      <DataState loading={sites.isLoading} error={sites.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Nom</th>
              <th scope="col">Type</th>
              <th scope="col">Fuseau</th>
              <th scope="col">Statut</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <SiteRow key={s.site_id} site={s} onEdit={() => setEditing(s)} onChanged={refresh} />
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}

function SiteRow({ site: s, onEdit, onChanged }: { site: Site; onEdit: () => void; onChanged: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  async function toggle() {
    setPending(true);
    setError(null);
    try {
      const options = { path: { site_id: s.site_id }, ifMatch: `"${s.row_version}"` };
      if (s.status === "ACTIVE") await call("post", "/sites/{site_id}/deactivate", options);
      else await call("post", "/sites/{site_id}/reactivate", options);
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <tr>
        <td>{s.code}</td>
        <td>{s.name}</td>
        <td>{label(SITE_TYPES, s.site_type)}</td>
        <td>{s.timezone ?? <span className="muted">fuseau de la société</span>}</td>
        <td>
          <Badge tone={s.status === "ACTIVE" ? "ok" : "neutral"}>{s.status === "ACTIVE" ? "Actif" : "Inactif"}</Badge>
        </td>
        <td className="actions">
          <button type="button" onClick={onEdit}>
            Modifier
          </button>
          <button type="button" disabled={pending} onClick={() => void toggle()}>
            {s.status === "ACTIVE" ? "Désactiver" : "Réactiver"}
          </button>
        </td>
      </tr>
      {error !== null && (
        <tr className="subrow">
          <td colSpan={6}>
            <ErrorMessage error={error} />
          </td>
        </tr>
      )}
    </>
  );
}

function SiteForm({ site, onDone, onCancel }: { site?: Site; onDone: () => void; onCancel: () => void }) {
  const [form, setForm] = useState({
    code: site?.code ?? "",
    name: site?.name ?? "",
    site_type: site?.site_type ?? "MINE",
    timezone: site?.timezone ?? "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const siteType = form.site_type as Schemas["SiteCreate"]["site_type"];
  return (
    <ActionForm
      title={site ? `Modifier le site ${site.code}` : "Nouveau site"}
      submitLabel={site ? "Enregistrer" : "Créer le site"}
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        site
          ? call("patch", "/sites/{site_id}", {
              path: { site_id: site.site_id },
              ifMatch: `"${site.row_version}"`,
              body: { name: form.name.trim(), site_type: siteType, timezone: orNull(form.timezone) },
            })
          : call("post", "/sites", {
              body: { code: form.code.trim(), name: form.name.trim(), site_type: siteType, timezone: orNull(form.timezone) },
            })
      }
    >
      {!site && (
        <label>
          Code (unique, définitif)
          <input required pattern="[A-Za-z0-9_\-]{1,32}" maxLength={32} value={form.code} onChange={set("code")} />
        </label>
      )}
      <label>
        Nom
        <input required minLength={2} maxLength={120} value={form.name} onChange={set("name")} />
      </label>
      <label>
        Type
        <select value={form.site_type} onChange={set("site_type")}>
          <Options map={SITE_TYPES} />
        </select>
      </label>
      <label>
        Fuseau horaire
        <select value={form.timezone} onChange={set("timezone")}>
          <option value="">Celui de la société</option>
          {TIMEZONES.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </label>
    </ActionForm>
  );
}

// --- Utilisateurs et rôles -----------------------------------------------------------------------------

type User = Schemas["UserOut"];

function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: () => read("/roles") });
}

export function UsersAdminPage() {
  const me = useMe();
  if (!can(me.grants, "identity.user.read")) return <Denied />;
  return <UsersAdmin />;
}

function UsersAdmin() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [inviting, setInviting] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const users = useQuery({
    queryKey: ["users", status, page],
    queryFn: () =>
      read("/users", {
        query: { status: (status || null) as "INVITED" | "ACTIVE" | "DISABLED" | null, page, page_size: 50 },
      }),
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["users"] });
  const items = users.data?.items ?? [];
  const canInvite = can(me.grants, "identity.user.create");
  return (
    <>
      {canInvite && !inviting && (
        <button type="button" className="primary" onClick={() => setInviting(true)}>
          Inviter un utilisateur
        </button>
      )}
      {inviting && (
        <InviteUser
          onDone={() => {
            setInviting(false);
            refresh();
          }}
          onCancel={() => setInviting(false)}
        />
      )}
      <div className="filters">
        <label>
          Statut
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <Options map={USER_STATUS} empty="Tous" />
          </select>
        </label>
      </div>
      <DataState loading={users.isLoading} error={users.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Nom</th>
              <th scope="col">E-mail</th>
              <th scope="col">Statut</th>
              <th scope="col">Dernière connexion</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.user_account_id}>
                <td>
                  <button
                    type="button"
                    className="link"
                    aria-expanded={selected === u.user_account_id}
                    onClick={() => setSelected(selected === u.user_account_id ? null : u.user_account_id)}
                  >
                    {u.display_name}
                  </button>
                </td>
                <td>{u.email ?? <span className="muted">masqué</span>}</td>
                <td>
                  <Badge tone={u.status === "ACTIVE" ? "ok" : u.status === "INVITED" ? "warn" : "neutral"}>
                    {label(USER_STATUS, u.status)}
                  </Badge>
                </td>
                <td>
                  {formatDateTime(u.last_login_at, me.timezone)}
                  {u.mfa_enabled && <div className="small muted">Double authentification active</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={50} total={users.data?.total ?? 0} onPage={setPage} />
      </DataState>
      {selected && <UserPanel userId={selected} onChanged={refresh} />}
    </>
  );
}

function ScopeFields({
  roleCode,
  scope,
  siteId,
  onScope,
  onSite,
}: {
  roleCode: string;
  scope: string;
  siteId: string;
  onScope: (v: string) => void;
  onSite: (v: string) => void;
}) {
  const roles = useRoles();
  const { sites } = useSites();
  const allowed = roles.data?.find((r) => r.role_code === roleCode)?.allowed_scopes ?? [];
  return (
    <>
      <label>
        Portée
        <select value={scope} onChange={(e) => onScope(e.target.value)}>
          {allowed
            .filter((s) => s in SCOPES)
            .map((s) => (
              <option key={s} value={s}>
                {SCOPES[s]}
              </option>
            ))}
        </select>
      </label>
      {scope === "SITE" && (
        <label>
          Site
          <select required value={siteId} onChange={(e) => onSite(e.target.value)}>
            <option value="">— Choisir —</option>
            {sites
              .filter((s) => s.status === "ACTIVE")
              .map((s) => (
                <option key={s.site_id} value={s.site_id}>
                  {s.code} — {s.name}
                </option>
              ))}
          </select>
        </label>
      )}
    </>
  );
}

function RoleSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const roles = useRoles();
  return (
    <label>
      Rôle
      <select required value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">— Choisir —</option>
        {(roles.data ?? [])
          .filter((r) => r.role_code !== "PLATFORM_ADMIN")
          .map((r) => (
            <option key={r.role_code} value={r.role_code}>
              {r.label_fr}
            </option>
          ))}
      </select>
    </label>
  );
}

function useRoleScope() {
  const roles = useRoles();
  const [role, setRole] = useState("");
  const [scope, setScope] = useState("TENANT");
  const [siteId, setSiteId] = useState("");
  const changeRole = (code: string) => {
    setRole(code);
    const allowed = roles.data?.find((r) => r.role_code === code)?.allowed_scopes ?? [];
    setScope(allowed.includes("TENANT") ? "TENANT" : "SITE");
  };
  return { role, scope, siteId, changeRole, setScope, setSiteId };
}

function InviteUser({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const rs = useRoleScope();
  return (
    <ActionForm
      title="Inviter un utilisateur"
      submitLabel="Envoyer l'invitation"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/users", {
          body: {
            email: email.trim(),
            display_name: name.trim(),
            phone: orNull(phone),
            role_code: rs.role,
            scope_type: rs.scope as "TENANT" | "SITE",
            site_id: rs.scope === "SITE" ? rs.siteId : null,
          },
        })
      }
    >
      <label>
        Adresse e-mail
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Nom affiché
        <input required minLength={2} maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Téléphone (facultatif, +224…)
        <input type="tel" pattern={PHONE_PATTERN} value={phone} onChange={(e) => setPhone(e.target.value)} />
      </label>
      <RoleSelect value={rs.role} onChange={rs.changeRole} />
      {rs.role && (
        <ScopeFields roleCode={rs.role} scope={rs.scope} siteId={rs.siteId} onScope={rs.setScope} onSite={rs.setSiteId} />
      )}
      <p className="muted small">Un lien d'activation à usage unique est envoyé par e-mail.</p>
    </ActionForm>
  );
}

function UserPanel({ userId, onChanged }: { userId: string; onChanged: () => void }) {
  const me = useMe();
  const queryClient = useQueryClient();
  const roles = useRoles();
  const { sites } = useSites();
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const user = useQuery({
    queryKey: ["user", userId],
    queryFn: () => call("get", "/users/{user_id}", { path: { user_id: userId } }),
  });
  const grants = useQuery({
    queryKey: ["user-roles", userId],
    enabled: can(me.grants, "identity.role_assignment.read"),
    queryFn: () => read("/role-assignments", { query: { user_id: userId, page_size: 200 } }),
  });
  const u: User | undefined = user.data?.data;
  const refresh = () => {
    setAdding(false);
    void queryClient.invalidateQueries({ queryKey: ["user", userId] });
    void queryClient.invalidateQueries({ queryKey: ["user-roles", userId] });
    onChanged();
  };
  async function run(action: () => Promise<unknown>, done: string) {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(done);
      refresh();
    } catch (err) {
      setError(err);
    }
  }
  if (!u) return <DataState loading={user.isLoading} error={user.error} empty={false}>{null}</DataState>;
  const self = u.user_account_id === me.user_account_id;
  const path = { path: { user_id: u.user_account_id } };
  const roleLabel = new Map((roles.data ?? []).map((r) => [r.role_code, r.label_fr]));
  const siteName = new Map(sites.map((s) => [s.site_id, s.code]));
  return (
    <div className="card">
      <h2>{u.display_name}</h2>
      <div className="toolbar">
        {u.status === "INVITED" && can(me.grants, "identity.user.create") && (
          <button
            type="button"
            onClick={() => void run(() => call("post", "/users/{user_id}/resend-invitation", path), "Invitation renvoyée.")}
          >
            Renvoyer l'invitation
          </button>
        )}
        {u.status === "ACTIVE" && can(me.grants, "identity.user.reset_credentials") && (
          <button
            type="button"
            onClick={() =>
              void run(
                () => call("post", "/users/{user_id}/reset-credentials", path),
                "Lien de réinitialisation envoyé à l'utilisateur.",
              )
            }
          >
            Réinitialiser le mot de passe
          </button>
        )}
        {!self && u.mfa_enabled && can(me.grants, "identity.user.reset_mfa") && (
          <button
            type="button"
            onClick={() =>
              void run(
                () =>
                  call("post", "/users/{user_id}/reset-mfa", { ...path, ifMatch: `"${u.row_version}"` }),
                "Double authentification retirée : l'utilisateur la reconfigurera à sa prochaine connexion.",
              )
            }
          >
            Réinitialiser la double authentification
          </button>
        )}
        {!self && can(me.grants, "identity.user.deactivate") && (
          <button
            type="button"
            onClick={() =>
              void run(
                () =>
                  u.status === "DISABLED"
                    ? call("post", "/users/{user_id}/reactivate", { ...path, ifMatch: `"${u.row_version}"` })
                    : call("post", "/users/{user_id}/deactivate", { ...path, ifMatch: `"${u.row_version}"` }),
                u.status === "DISABLED" ? "Compte réactivé." : "Compte désactivé : ses sessions sont fermées.",
              )
            }
          >
            {u.status === "DISABLED" ? "Réactiver le compte" : "Désactiver le compte"}
          </button>
        )}
        {!self && can(me.grants, "identity.role_assignment.create") && !adding && (
          <button type="button" onClick={() => setAdding(true)}>
            Ajouter un rôle
          </button>
        )}
      </div>
      {self && <p className="muted small">Vous ne pouvez pas modifier vos propres droits ni désactiver votre compte.</p>}
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      {error !== null && <ErrorMessage error={error} />}
      {adding && <AddRole userId={u.user_account_id} onDone={refresh} onCancel={() => setAdding(false)} />}
      <h3>Rôles</h3>
      <DataState loading={grants.isLoading} error={grants.error} empty={(grants.data?.items ?? []).length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Rôle</th>
              <th scope="col">Portée</th>
              <th scope="col">Depuis</th>
              {!self && can(me.grants, "identity.role_assignment.revoke") && <th scope="col">Action</th>}
            </tr>
          </thead>
          <tbody>
            {(grants.data?.items ?? []).map((g) => (
              <tr key={g.user_role_assignment_id}>
                <td>{roleLabel.get(g.role_code) ?? g.role_code}</td>
                <td>{g.scope_type === "SITE" ? `Site ${siteName.get(g.site_id ?? "") ?? ""}` : "Toute la société"}</td>
                <td>{formatDateTime(g.valid_from, me.timezone)}</td>
                {!self && can(me.grants, "identity.role_assignment.revoke") && (
                  <td>
                    <button
                      type="button"
                      onClick={() =>
                        void run(
                          () =>
                            call("post", "/role-assignments/{assignment_id}/revoke", {
                              path: { assignment_id: g.user_role_assignment_id },
                              ifMatch: `"${g.row_version}"`,
                            }),
                          "Rôle retiré.",
                        )
                      }
                    >
                      Retirer
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </div>
  );
}

function AddRole({ userId, onDone, onCancel }: { userId: string; onDone: () => void; onCancel: () => void }) {
  const rs = useRoleScope();
  return (
    <ActionForm
      title="Ajouter un rôle"
      submitLabel="Attribuer le rôle"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/role-assignments", {
          body: {
            user_account_id: userId,
            role_code: rs.role,
            scope_type: rs.scope as "TENANT" | "SITE",
            site_id: rs.scope === "SITE" ? rs.siteId : null,
          },
        })
      }
    >
      <RoleSelect value={rs.role} onChange={rs.changeRole} />
      {rs.role && (
        <ScopeFields roleCode={rs.role} scope={rs.scope} siteId={rs.siteId} onScope={rs.setScope} onSite={rs.setSiteId} />
      )}
    </ActionForm>
  );
}

// --- Journal d'audit -----------------------------------------------------------------------------------

const ENTITY_TYPES: Record<string, string> = {
  vehicle_assignment: "Affectation",
  vehicle: "Véhicule",
  driver: "Conducteur",
  driver_license: "Permis",
  driver_qualification: "Habilitation",
  site: "Site",
  user_account: "Utilisateur",
  user_role_assignment: "Rôle",
  tenant: "Société",
};

export function AuditAdminPage() {
  const me = useMe();
  if (!can(me.grants, "audit.event.read")) return <Denied />;
  return <AuditAdmin />;
}

function AuditAdmin() {
  const me = useMe();
  const [filters, setFilters] = useState({ entity_type: "", action: "", from: "", to: "" });
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const day = (value: string, end: boolean) =>
    value ? zonedInputToUtc(`${value}T${end ? "23:59" : "00:00"}`, me.timezone).toISOString() : null;
  const events = useQuery({
    queryKey: ["audit", filters, page],
    queryFn: () =>
      read("/audit-events", {
        query: {
          entity_type: orNull(filters.entity_type),
          action: orNull(filters.action),
          occurred_from: day(filters.from, false),
          occurred_to: day(filters.to, true),
          page,
          page_size: 50,
        },
      }),
  });
  const set = (key: keyof typeof filters) => (e: { target: { value: string } }) => {
    setFilters({ ...filters, [key]: e.target.value });
    setPage(1);
  };
  const items = events.data?.items ?? [];
  return (
    <>
      <div className="filters">
        <label>
          Type d'élément
          <select value={filters.entity_type} onChange={set("entity_type")}>
            <Options map={ENTITY_TYPES} empty="Tous" />
          </select>
        </label>
        <label>
          Action (ex. vehicle.retire)
          <input maxLength={100} value={filters.action} onChange={set("action")} />
        </label>
        <label>
          Du
          <input type="date" value={filters.from} onChange={set("from")} />
        </label>
        <label>
          Au
          <input type="date" value={filters.to} onChange={set("to")} />
        </label>
      </div>
      <DataState loading={events.isLoading} error={events.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Action</th>
              <th scope="col">Élément</th>
              <th scope="col">Résultat</th>
              <th scope="col">Détail</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => (
              <Fragment key={e.audit_event_id}>
                <tr>
                  <td>{formatDateTime(e.occurred_at, me.timezone)}</td>
                  <td>
                    <code>{e.action}</code>
                  </td>
                  <td>{label(ENTITY_TYPES, e.entity_type)}</td>
                  <td>
                    <Badge tone={e.outcome === "SUCCESS" ? "ok" : "bad"}>
                      {e.outcome === "SUCCESS" ? "Réussi" : "Refusé"}
                    </Badge>
                    {e.reason && <div className="small muted">{e.reason}</div>}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="link"
                      aria-expanded={open === e.audit_event_id}
                      onClick={() => setOpen(open === e.audit_event_id ? null : e.audit_event_id)}
                    >
                      {open === e.audit_event_id ? "Masquer" : "Voir"}
                    </button>
                  </td>
                </tr>
                {open === e.audit_event_id && (
                  <tr className="subrow">
                    <td colSpan={5}>
                      <p className="small">
                        Champs modifiés : {(e.changed_fields ?? []).join(", ") || "—"} · Requête : {e.request_id ?? "—"}
                      </p>
                      <pre className="small">
                        {JSON.stringify({ avant: e.before_data, après: e.after_data }, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={50} total={events.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </>
  );
}
