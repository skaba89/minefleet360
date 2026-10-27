import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage } from "../components/common";
import { ActionForm, Options } from "../components/forms";
import { label, LOCATION_KINDS } from "../lib/labels";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

type LocationKind = Schemas["LocationCreate"]["kind"];

/** Lieux (points de chargement, de déchargement…) par site et matières transportées (lot 2a). */
export function ReferentialsPage() {
  const me = useMe();
  if (!can(me.grants, "dispatch.location.manage") && !can(me.grants, "dispatch.material.manage")) {
    return (
      <p className="error" role="alert">
        Vous n'avez pas accès à cette partie de l'administration.
      </p>
    );
  }
  return (
    <>
      {can(me.grants, "dispatch.location.manage") && <Locations />}
      {can(me.grants, "dispatch.material.manage") && <Materials />}
    </>
  );
}

function StatusToggle({ active, onToggle }: { active: boolean; onToggle: () => Promise<unknown> }) {
  const [error, setError] = useState<unknown>(null);
  return (
    <>
      <button type="button" onClick={() => onToggle().catch(setError)}>
        {active ? "Désactiver" : "Réactiver"}
      </button>
      {error !== null && <ErrorMessage error={error} />}
    </>
  );
}

function Locations() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { sites, siteId } = useSites();
  const [creating, setCreating] = useState(false);
  const locations = useQuery({
    queryKey: ["site-locations", "admin", siteId],
    queryFn: () => read("/site-locations", { query: { site_id: siteId, include_inactive: true } }),
  });
  const refresh = () => {
    setCreating(false);
    void queryClient.invalidateQueries({ queryKey: ["site-locations"] });
  };
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const allowedSites = sites.filter((s) => s.status === "ACTIVE" && can(me.grants, "dispatch.location.manage", s.site_id));
  return (
    <>
      <div className="page-head">
        <h2>Lieux des sites</h2>
        {!creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouveau lieu
          </button>
        )}
      </div>
      {creating && <CreateLocation sites={allowedSites} defaultSite={siteId} onDone={refresh} onCancel={() => setCreating(false)} />}
      <DataState
        loading={locations.isLoading}
        error={locations.error}
        empty={(locations.data ?? []).length === 0}
        emptyText="Aucun lieu : déclarez au moins un point de chargement et un point de déchargement par site."
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Site</th>
              <th scope="col">Code</th>
              <th scope="col">Nom</th>
              <th scope="col">Type</th>
              <th scope="col">Statut</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {(locations.data ?? []).map((loc) => (
              <tr key={loc.site_location_id}>
                <td>{siteCode.get(loc.site_id)}</td>
                <td>{loc.code}</td>
                <td>{loc.name}</td>
                <td>{label(LOCATION_KINDS, loc.kind)}</td>
                <td>
                  <Badge tone={loc.status === "ACTIVE" ? "ok" : "neutral"}>{loc.status === "ACTIVE" ? "Actif" : "Inactif"}</Badge>
                </td>
                <td>
                  <StatusToggle
                    active={loc.status === "ACTIVE"}
                    onToggle={async () => {
                      await call("patch", "/site-locations/{site_location_id}", {
                        path: { site_location_id: loc.site_location_id },
                        ifMatch: `"${loc.row_version}"`,
                        body: { status: loc.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" },
                      });
                      refresh();
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}

function CreateLocation({
  sites,
  defaultSite,
  onDone,
  onCancel,
}: {
  sites: Schemas["SiteOut"][];
  defaultSite: string | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    site_id: defaultSite ?? sites[0]?.site_id ?? "",
    code: "",
    name: "",
    kind: "LOADING_POINT",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  return (
    <ActionForm
      title="Nouveau lieu"
      submitLabel="Créer le lieu"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/site-locations", {
          body: { site_id: form.site_id, code: form.code.trim(), name: form.name.trim(), kind: form.kind as LocationKind },
        })
      }
    >
      <label>
        Site
        <select required value={form.site_id} onChange={set("site_id")}>
          {sites.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Code (unique sur le site)
        <input required pattern="[A-Za-z0-9_\-]{1,32}" maxLength={32} value={form.code} onChange={set("code")} />
      </label>
      <label>
        Nom
        <input required minLength={2} maxLength={120} value={form.name} onChange={set("name")} />
      </label>
      <label>
        Type
        <select value={form.kind} onChange={set("kind")}>
          <Options map={LOCATION_KINDS} />
        </select>
      </label>
    </ActionForm>
  );
}

function Materials() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", is_waste: false });
  const materials = useQuery({
    queryKey: ["materials", "admin"],
    queryFn: () => read("/materials", { query: { include_inactive: true } }),
  });
  const refresh = () => {
    setCreating(false);
    setForm({ code: "", name: "", is_waste: false });
    void queryClient.invalidateQueries({ queryKey: ["materials"] });
  };
  return (
    <>
      <div className="page-head">
        <h2>Matières transportées</h2>
        {!creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouvelle matière
          </button>
        )}
      </div>
      {creating && (
        <ActionForm
          title="Nouvelle matière"
          submitLabel="Créer la matière"
          onCancel={() => setCreating(false)}
          onDone={refresh}
          onSubmit={() =>
            call("post", "/materials", { body: { code: form.code.trim(), name: form.name.trim(), is_waste: form.is_waste } })
          }
        >
          <label>
            Code (unique)
            <input
              required
              pattern="[A-Za-z0-9_\-]{1,32}"
              maxLength={32}
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
          </label>
          <label>
            Nom
            <input required minLength={2} maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={form.is_waste} onChange={(e) => setForm({ ...form, is_waste: e.target.checked })} />
            Stérile (non valorisé)
          </label>
        </ActionForm>
      )}
      <DataState loading={materials.isLoading} error={materials.error} empty={(materials.data ?? []).length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Nom</th>
              <th scope="col">Nature</th>
              <th scope="col">Statut</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {(materials.data ?? []).map((m) => (
              <tr key={m.material_id}>
                <td>{m.code}</td>
                <td>{m.name}</td>
                <td>{m.is_waste ? "Stérile" : "Minerai / produit"}</td>
                <td>
                  <Badge tone={m.status === "ACTIVE" ? "ok" : "neutral"}>{m.status === "ACTIVE" ? "Active" : "Inactive"}</Badge>
                </td>
                <td>
                  <StatusToggle
                    active={m.status === "ACTIVE"}
                    onToggle={async () => {
                      await call("patch", "/materials/{material_id}", {
                        path: { material_id: m.material_id },
                        ifMatch: `"${m.row_version}"`,
                        body: { status: m.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" },
                      });
                      refresh();
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}
