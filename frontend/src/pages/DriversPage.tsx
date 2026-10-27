import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, Pager } from "../components/common";
import { ActionForm, Options, orNull } from "../components/forms";
import { DRIVER_STATUS, EMPLOYMENT, label } from "../lib/labels";
import { can } from "../lib/permissions";
import { useSites } from "../site/SiteContext";

const PAGE_SIZE = 50;
export type DriverStatusCode = Schemas["DriverStatusChange"]["status"];
export const DRIVER_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  ACTIVE: "ok",
  UNAVAILABLE: "warn",
  SUSPENDED: "bad",
  INACTIVE: "neutral",
};
// Format international imposé par le serveur (E.164) : +224 suivi du numéro, sans espace.
export const PHONE_PATTERN = "\\+[1-9][0-9]{6,14}";

export function DriversPage() {
  const me = useMe();
  const { siteId, sites } = useSites();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const drivers = useQuery({
    queryKey: ["drivers", siteId, status, search, page],
    queryFn: () =>
      read("/drivers", {
        query: {
          site_id: siteId,
          status: (status || null) as DriverStatusCode | null,
          q: search.trim() || null,
          page,
          page_size: PAGE_SIZE,
        },
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = drivers.data?.items ?? [];

  return (
    <section>
      <div className="page-head">
        <h1>Conducteurs</h1>
        {can(me.grants, "workforce.driver.create") && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouveau conducteur
          </button>
        )}
      </div>
      {creating && <CreateDriver onClose={() => setCreating(false)} />}
      <div className="filters">
        <label>
          Recherche (nom, matricule)
          <input
            type="search"
            value={search}
            maxLength={60}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </label>
        <label>
          Statut
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <Options map={DRIVER_STATUS} empty="Tous" />
          </select>
        </label>
      </div>
      <DataState loading={drivers.isLoading} error={drivers.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Nom</th>
              <th scope="col">Matricule</th>
              <th scope="col">Site</th>
              <th scope="col">Statut</th>
              <th scope="col">Engins habilités</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.driver_id}>
                <td>
                  <Link to={`/conducteurs/${d.driver_id}`}>
                    {d.last_name.toUpperCase()} {d.first_name}
                  </Link>
                </td>
                <td>{d.employee_number}</td>
                <td>{siteCode.get(d.site_id) ?? "—"}</td>
                <td>
                  <Badge tone={DRIVER_TONE[d.status] ?? "neutral"}>{label(DRIVER_STATUS, d.status)}</Badge>
                </td>
                <td>{d.authorized_category_ids?.length ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={drivers.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function CreateDriver({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { sites, siteId } = useSites();
  const allowedSites = sites.filter(
    (s) => s.status === "ACTIVE" && can(me.grants, "workforce.driver.create", s.site_id),
  );
  const [form, setForm] = useState({
    site_id: siteId ?? allowedSites[0]?.site_id ?? "",
    employee_number: "",
    last_name: "",
    first_name: "",
    phone: "",
    employment_type: "EMPLOYEE",
    external_company_name: "",
    hire_date: "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  return (
    <ActionForm
      title="Nouveau conducteur"
      submitLabel="Créer le conducteur"
      onCancel={onClose}
      onSubmit={async () => {
        const { data } = await call("post", "/drivers", {
          body: {
            site_id: form.site_id,
            employee_number: form.employee_number.trim(),
            last_name: form.last_name.trim(),
            first_name: form.first_name.trim(),
            phone: orNull(form.phone),
            employment_type: form.employment_type as Schemas["DriverCreate"]["employment_type"],
            external_company_name: orNull(form.external_company_name),
            hire_date: orNull(form.hire_date),
          },
        });
        await queryClient.invalidateQueries({ queryKey: ["drivers"] });
        // Homonyme sur le même site : avertissement non bloquant (US-1.16 A6), affiché sur la fiche.
        const possibleDuplicate = data.warnings?.includes("POSSIBLE_DUPLICATE") ?? false;
        navigate(`/conducteurs/${data.driver_id}`, { state: { possibleDuplicate } });
      }}
    >
      <label>
        Site de rattachement
        <select required value={form.site_id} onChange={set("site_id")}>
          <option value="">— Choisir —</option>
          {allowedSites.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Matricule (unique)
        <input required pattern="[A-Za-z0-9_\-]{1,30}" maxLength={30} value={form.employee_number} onChange={set("employee_number")} />
      </label>
      <label>
        Nom
        <input required maxLength={80} value={form.last_name} onChange={set("last_name")} />
      </label>
      <label>
        Prénom
        <input required maxLength={80} value={form.first_name} onChange={set("first_name")} />
      </label>
      <label>
        Téléphone (+224…)
        <input type="tel" pattern={PHONE_PATTERN} value={form.phone} onChange={set("phone")} />
      </label>
      <label>
        Contrat
        <select value={form.employment_type} onChange={set("employment_type")}>
          <Options map={EMPLOYMENT} />
        </select>
      </label>
      {form.employment_type === "SUBCONTRACTOR" && (
        <label>
          Entreprise sous-traitante
          <input required maxLength={120} value={form.external_company_name} onChange={set("external_company_name")} />
        </label>
      )}
      <label>
        Date d'embauche
        <input type="date" value={form.hire_date} onChange={set("hire_date")} />
      </label>
    </ActionForm>
  );
}
