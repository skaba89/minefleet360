import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { get, type Schemas } from "../api/client";
import { Badge, DataState, Pager } from "../components/common";
import { label, VEHICLE_STATUS } from "../lib/labels";
import { useSites } from "../site/SiteContext";

const PAGE_SIZE = 50;
const TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  AVAILABLE: "ok",
  IN_MAINTENANCE: "warn",
  IMMOBILIZED: "bad",
  OUT_OF_SERVICE: "bad",
  RETIRED: "neutral",
};

export function VehiclesPage() {
  const { siteId, sites } = useSites();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const vehicles = useQuery({
    queryKey: ["vehicles", siteId, status, page],
    queryFn: () =>
      get<Schemas["Page_VehicleOut_"]>("/vehicles", {
        site_id: siteId,
        status: status || null,
        page,
        page_size: PAGE_SIZE,
      }),
  });
  const categories = useQuery({
    queryKey: ["vehicle-categories"],
    queryFn: () => get<Schemas["VehicleCategoryOut"][]>("/vehicle-categories"),
  });
  const categoryLabel = new Map((categories.data ?? []).map((c) => [c.vehicle_category_id, c.label_fr]));
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = vehicles.data?.items ?? [];

  return (
    <section>
      <h1>Véhicules et engins</h1>
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
            <option value="">Tous (hors réformés)</option>
            {Object.entries(VEHICLE_STATUS).map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
      </div>
      <DataState loading={vehicles.isLoading} error={vehicles.error} empty={items.length === 0}>
        <table>
          <thead>
            <tr>
              <th scope="col">N° de parc</th>
              <th scope="col">Catégorie</th>
              <th scope="col">Immatriculation</th>
              <th scope="col">Site</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {items.map((v) => (
              <tr key={v.vehicle_id}>
                <td>{v.fleet_number}</td>
                <td>{categoryLabel.get(v.vehicle_category_id) ?? "—"}</td>
                <td>{v.registration_number ?? "—"}</td>
                <td>{siteCode.get(v.site_id) ?? "—"}</td>
                <td>
                  <Badge tone={TONE[v.status] ?? "neutral"}>{label(VEHICLE_STATUS, v.status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={vehicles.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}
