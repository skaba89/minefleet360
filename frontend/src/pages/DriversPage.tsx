import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get, type Schemas } from "../api/client";
import { Badge, DataState, Pager } from "../components/common";
import { DRIVER_STATUS, label } from "../lib/labels";
import { useSites } from "../site/SiteContext";

const PAGE_SIZE = 50;

export function DriversPage() {
  const { siteId, sites } = useSites();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const drivers = useQuery({
    queryKey: ["drivers", siteId, status, search, page],
    queryFn: () =>
      get<Schemas["Page_DriverOut_"]>("/drivers", {
        site_id: siteId,
        status: status || null,
        q: search.trim() || null,
        page,
        page_size: PAGE_SIZE,
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = drivers.data?.items ?? [];

  return (
    <section>
      <h1>Conducteurs</h1>
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
            <option value="">Tous</option>
            {Object.entries(DRIVER_STATUS).map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
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
                  {d.last_name.toUpperCase()} {d.first_name}
                </td>
                <td>{d.employee_number}</td>
                <td>{siteCode.get(d.site_id) ?? "—"}</td>
                <td>
                  <Badge tone={d.status === "ACTIVE" ? "ok" : "warn"}>{label(DRIVER_STATUS, d.status)}</Badge>
                </td>
                <td>{d.authorized_category_ids.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={drivers.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}
