import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, Pager } from "../components/common";
import { ExportButton } from "../components/ExportButton";
import { ActionForm, Fact, Options, orNull } from "../components/forms";
import { downloadCsv, fetchAllPages, stamp, toCsv } from "../lib/csv";
import {
  label,
  TYRE_ALERTS,
  TYRE_CATEGORY,
  TYRE_DISMOUNT_REASONS,
  TYRE_EVENTS,
  TYRE_SCRAP_REASONS,
  TYRE_STATUS,
  TYRE_TONE,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Tyre = Schemas["TyreOut"];
type Status = Tyre["status"];
const PAGE_SIZE = 50;
const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });

function amount(value: string | null | undefined, currency: string | null | undefined): string {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(Number(value))}${currency ? ` ${currency}` : ""}`;
}

function Alerts({ tyre }: { tyre: Tyre }) {
  if (tyre.alerts.length === 0) return null;
  return (
    <>
      {tyre.alerts.map((a) => (
        <div key={a}>
          <Badge tone={a === "TREAD_AT_LIMIT" ? "bad" : "warn"}>{label(TYRE_ALERTS, a)}</Badge>
        </div>
      ))}
    </>
  );
}

/** Parc de pneus : état, position, usure et alertes de maintenance. */
export function TyresPage() {
  const me = useMe();
  const { siteId, sites } = useSites();
  const [status, setStatus] = useState("");
  const [alertOnly, setAlertOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const tyres = useQuery({
    queryKey: ["tyres", siteId, status, alertOnly, page],
    queryFn: () =>
      read("/tyres", {
        query: { site_id: siteId, status: (status || null) as Status | null, alert_only: alertOnly, page, page_size: PAGE_SIZE },
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = tyres.data?.items ?? [];
  return (
    <section>
      <div className="page-head">
        <h1>Pneus</h1>
        {can(me.grants, "maintenance.tyre.manage", siteId) && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Enregistrer un pneu
          </button>
        )}
      </div>
      {creating && <CreateTyreForm onClose={() => setCreating(false)} />}
      <div className="filters">
        <label>
          État
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
          >
            <Options map={TYRE_STATUS} empty="Tous" />
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={alertOnly}
            onChange={(e) => {
              setAlertOnly(e.target.checked);
              setPage(1);
            }}
          />
          Avec alerte seulement
        </label>
        <ExportButton
          run={async () => {
            const { items, truncated } = await fetchAllPages((p, size) =>
              read("/tyres", {
                query: { site_id: siteId, status: (status || null) as Status | null, alert_only: alertOnly, page: p, page_size: size },
              }),
            );
            downloadCsv(
              `pneus-${stamp()}.csv`,
              toCsv(
                ["Marque", "N° de série", "Modèle", "Dimension", "Catégorie", "Site", "État", "Engin", "Position",
                  "Sculpture (mm)", "Limite de rebut (mm)", "Rechapages", "Alertes", "Km mesurés", "Heures mesurées",
                  "Coût total", "Coût/km", "Coût/heure", "Devise"],
                items.map((t) => [
                  t.brand, t.serial_number, t.model, t.size, label(TYRE_CATEGORY, t.category), siteCode.get(t.site_id) ?? t.site_id,
                  label(TYRE_STATUS, t.status), t.vehicle_fleet_number ?? "", t.position_code ?? "", t.last_tread_mm ?? "",
                  t.scrap_tread_mm, t.retread_count, t.alerts.map((a) => label(TYRE_ALERTS, a)).join(" ; "), t.km_run,
                  t.hours_run, t.total_cost ?? "", t.cost_per_km ?? "", t.cost_per_hour ?? "", t.currency ?? "",
                ]),
              ),
            );
            return { truncated };
          }}
        />
      </div>
      <DataState loading={tyres.isLoading} error={tyres.error} empty={items.length === 0} emptyText="Aucun pneu.">
        <table>
          <thead>
            <tr>
              <th scope="col">Pneu</th>
              <th scope="col">Dimension</th>
              <th scope="col">Engin / position</th>
              <th scope="col">Sculpture</th>
              <th scope="col">Coût / km</th>
              <th scope="col">État</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.tyre_id}>
                <td>
                  <Link to={`/pneus/${t.tyre_id}`}>
                    {t.brand} {t.serial_number}
                  </Link>
                  <div className="small muted">
                    {siteCode.get(t.site_id)} — {label(TYRE_CATEGORY, t.category)}
                  </div>
                </td>
                <td>{t.size}</td>
                <td>{t.vehicle_fleet_number ? `${t.vehicle_fleet_number} · ${t.position_code}` : "—"}</td>
                <td>
                  {t.last_tread_mm != null ? `${number.format(Number(t.last_tread_mm))} mm` : "—"}
                  <Alerts tyre={t} />
                </td>
                <td>{t.cost_per_km ? amount(t.cost_per_km, t.currency) : "Données insuffisantes"}</td>
                <td>
                  <Badge tone={TYRE_TONE[t.status] ?? "neutral"}>{label(TYRE_STATUS, t.status)}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} pageSize={PAGE_SIZE} total={tyres.data?.total ?? 0} onPage={setPage} />
      </DataState>
    </section>
  );
}

function CreateTyreForm({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { siteId, sites } = useSites();
  const allowed = sites.filter((s) => can(me.grants, "maintenance.tyre.manage", s.site_id));
  const [draft, setForm] = useState({
    site_id: "",
    serial_number: "",
    brand: "",
    model: "",
    size: "",
    category: "DRIVE",
    purchase_cost: "",
    currency: "GNF",
    initial_tread_mm: "",
    scrap_tread_mm: "",
    nominal_pressure_kpa: "",
  });
  // Site calculé à chaque affichage : la liste des sites peut arriver après l'ouverture du formulaire.
  const form = { ...draft, site_id: draft.site_id || siteId || allowed[0]?.site_id || "" };
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch });
  return (
    <ActionForm
      title="Enregistrer un pneu"
      submitLabel="Enregistrer"
      onCancel={onClose}
      onSubmit={async () => {
        const cost = orNull(form.purchase_cost);
        const { data } = await call("post", "/tyres", {
          body: {
            site_id: form.site_id,
            serial_number: form.serial_number.trim(),
            brand: form.brand.trim(),
            model: form.model.trim(),
            size: form.size.trim(),
            category: form.category as Schemas["TyreCreate"]["category"],
            purchase_cost: cost,
            currency: cost ? form.currency.trim().toUpperCase() : null,
            initial_tread_mm: form.initial_tread_mm,
            scrap_tread_mm: form.scrap_tread_mm,
            nominal_pressure_kpa: form.nominal_pressure_kpa ? Number(form.nominal_pressure_kpa) : null,
          },
        });
        void queryClient.invalidateQueries({ queryKey: ["tyres"] });
        navigate(`/pneus/${data.tyre_id}`);
      }}
    >
      <label>
        Site
        <select required value={form.site_id} onChange={(e) => set({ site_id: e.target.value })}>
          <option value="">— Choisir —</option>
          {allowed.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Marque
        <input required maxLength={64} value={form.brand} onChange={(e) => set({ brand: e.target.value })} />
      </label>
      <label>
        N° de série
        <input required maxLength={64} value={form.serial_number} onChange={(e) => set({ serial_number: e.target.value })} />
      </label>
      <label>
        Modèle
        <input required maxLength={64} value={form.model} onChange={(e) => set({ model: e.target.value })} />
      </label>
      <label>
        Dimension
        <input required maxLength={32} placeholder="27.00R49" value={form.size} onChange={(e) => set({ size: e.target.value })} />
      </label>
      <label>
        Catégorie
        <select value={form.category} onChange={(e) => set({ category: e.target.value })}>
          <Options map={TYRE_CATEGORY} />
        </select>
      </label>
      <label>
        Sculpture neuve (mm)
        <input required type="number" step="0.1" min="0.1" max="300" value={form.initial_tread_mm} onChange={(e) => set({ initial_tread_mm: e.target.value })} />
      </label>
      <label>
        Limite de rebut (mm)
        <input required type="number" step="0.1" min="0" max="300" value={form.scrap_tread_mm} onChange={(e) => set({ scrap_tread_mm: e.target.value })} />
      </label>
      <label>
        Pression nominale (kPa, facultatif)
        <input type="number" min="1" max="2000" value={form.nominal_pressure_kpa} onChange={(e) => set({ nominal_pressure_kpa: e.target.value })} />
      </label>
      <label>
        Coût d'achat (facultatif)
        <input type="number" step="0.01" min="0" value={form.purchase_cost} onChange={(e) => set({ purchase_cost: e.target.value })} />
      </label>
      <label>
        Devise
        <input maxLength={3} value={form.currency} onChange={(e) => set({ currency: e.target.value })} />
      </label>
    </ActionForm>
  );
}

type Panel = "mount" | "dismount" | "inspect" | "send" | "return" | "scrap" | null;

/** Fiche d'un pneu : actions selon l'état et le rôle, coûts au km/heure, historique complet. */
export function TyrePage() {
  const { tyreId = "" } = useParams();
  const me = useMe();
  const queryClient = useQueryClient();
  const { timezoneOf } = useSites();
  const [panel, setPanel] = useState<Panel>(null);
  const tyre = useQuery({
    queryKey: ["tyre", tyreId],
    queryFn: () => call("get", "/tyres/{tyre_id}", { path: { tyre_id: tyreId } }),
  });
  const t = tyre.data?.data;
  const etag = tyre.data?.etag ?? null;
  const tz = timezoneOf(t?.site_id);
  const canFit = t ? can(me.grants, "maintenance.tyre.fit", t.site_id) : false;
  const canManage = t ? can(me.grants, "maintenance.tyre.manage", t.site_id) : false;
  const done = async () => {
    setPanel(null);
    await queryClient.invalidateQueries({ queryKey: ["tyre", tyreId] });
    void queryClient.invalidateQueries({ queryKey: ["tyres"] });
  };
  async function post(path: "mount" | "dismount" | "inspections" | "repair" | "scrap", body: unknown) {
    await call("post", `/tyres/{tyre_id}/${path}` as "/tyres/{tyre_id}/mount", {
      path: { tyre_id: tyreId },
      ifMatch: etag,
      body: body as Schemas["TyreMount"],
    });
    await done();
  }
  return (
    <section>
      <Link className="back" to="/pneus">
        ← Pneus
      </Link>
      <DataState loading={tyre.isLoading} error={tyre.error} empty={!t}>
        {t && (
          <>
            <div className="page-head">
              <h1>
                {t.brand} {t.serial_number} <Badge tone={TYRE_TONE[t.status] ?? "neutral"}>{label(TYRE_STATUS, t.status)}</Badge>
              </h1>
            </div>
            <div className="toolbar">
              {canFit && t.status === "IN_STOCK" && (
                <button type="button" className="primary" onClick={() => setPanel("mount")}>
                  Monter sur un engin
                </button>
              )}
              {canFit && t.status === "MOUNTED" && (
                <button type="button" onClick={() => setPanel("dismount")}>
                  Démonter
                </button>
              )}
              {canFit && (t.status === "IN_STOCK" || t.status === "MOUNTED") && (
                <button type="button" onClick={() => setPanel("inspect")}>
                  Contrôler l'usure
                </button>
              )}
              {canManage && t.status === "IN_STOCK" && (
                <button type="button" onClick={() => setPanel("send")}>
                  Envoyer en réparation
                </button>
              )}
              {canManage && t.status === "IN_REPAIR" && (
                <button type="button" className="primary" onClick={() => setPanel("return")}>
                  Retour de réparation / rechapage
                </button>
              )}
              {canManage && (t.status === "IN_STOCK" || t.status === "IN_REPAIR") && (
                <button type="button" onClick={() => setPanel("scrap")}>
                  Mettre au rebut
                </button>
              )}
            </div>
            {panel === "mount" && <MountForm tyre={t} onCancel={() => setPanel(null)} onSubmit={(b) => post("mount", b)} />}
            {panel === "dismount" && <DismountForm onCancel={() => setPanel(null)} onSubmit={(b) => post("dismount", b)} />}
            {panel === "inspect" && <InspectForm mounted={t.status === "MOUNTED"} onCancel={() => setPanel(null)} onSubmit={(b) => post("inspections", b)} />}
            {panel === "send" && (
              <ActionForm title="Envoyer en réparation" submitLabel="Envoyer" onCancel={() => setPanel(null)} onSubmit={() => post("repair", { action: "SEND" })}>
                <p className="muted">Le coût se saisit au retour.</p>
              </ActionForm>
            )}
            {panel === "return" && <ReturnForm tyre={t} onCancel={() => setPanel(null)} onSubmit={(b) => post("repair", b)} />}
            {panel === "scrap" && <ScrapForm onCancel={() => setPanel(null)} onSubmit={(b) => post("scrap", b)} />}
            <dl className="facts">
              <Fact label="Modèle / dimension">{`${t.model} — ${t.size}`}</Fact>
              <Fact label="Catégorie">{label(TYRE_CATEGORY, t.category)}</Fact>
              <Fact label="Engin / position">
                {t.vehicle_id ? (
                  <Link to={`/vehicules/${t.vehicle_id}`}>
                    {t.vehicle_fleet_number} · {t.position_code}
                  </Link>
                ) : null}
              </Fact>
              <Fact label="Sculpture (neuve / limite / dernière)">
                {`${number.format(Number(t.initial_tread_mm))} / ${number.format(Number(t.scrap_tread_mm))} / ${t.last_tread_mm != null ? number.format(Number(t.last_tread_mm)) : "—"} mm`}
              </Fact>
              <Fact label="Pression (nominale / dernière)">
                {t.nominal_pressure_kpa || t.last_pressure_kpa ? `${t.nominal_pressure_kpa ?? "—"} / ${t.last_pressure_kpa ?? "—"} kPa` : null}
              </Fact>
              <Fact label="Dernier contrôle">{t.last_inspected_at ? formatDateTime(t.last_inspected_at, tz) : null}</Fact>
              <Fact label="Rechapages">{t.retread_count}</Fact>
              <Fact label="Alertes">{t.alerts.length ? <Alerts tyre={t} /> : "Aucune"}</Fact>
              <Fact label="Coût total (achat + réparations)">{t.cost_complete ? amount(t.total_cost, t.currency) : "Données insuffisantes : coût d'achat inconnu"}</Fact>
              <Fact label="Distance / heures mesurées">{`${number.format(Number(t.km_run))} km / ${number.format(Number(t.hours_run))} h`}</Fact>
              <Fact label="Coût au km">{t.cost_per_km ? amount(t.cost_per_km, t.currency) : "Données insuffisantes"}</Fact>
              <Fact label="Coût à l'heure">{t.cost_per_hour ? amount(t.cost_per_hour, t.currency) : "Données insuffisantes"}</Fact>
            </dl>
            <h2>Historique</h2>
            <ol className="timeline">
              {(t.events ?? []).map((e, i) => (
                <li key={`${e.occurred_at}-${i}`}>
                  <strong>{label(TYRE_EVENTS, e.event_type)}</strong> — {formatDateTime(e.occurred_at, tz)}
                  {e.position_code && <span> · position {e.position_code}</span>}
                  {e.odometer_km != null && <span> · {number.format(Number(e.odometer_km))} km</span>}
                  {e.hour_meter != null && <span> · {number.format(Number(e.hour_meter))} h</span>}
                  {e.tread_mm != null && <span> · {number.format(Number(e.tread_mm))} mm</span>}
                  {e.pressure_kpa != null && <span> · {e.pressure_kpa} kPa</span>}
                  {e.cost != null && <span> · {amount(e.cost, e.currency)}</span>}
                  {e.reason_code && <span className="muted"> ({label({ ...TYRE_DISMOUNT_REASONS, ...TYRE_SCRAP_REASONS }, e.reason_code)})</span>}
                  {e.note && <div className="small muted">{e.note}</div>}
                </li>
              ))}
            </ol>
          </>
        )}
      </DataState>
    </section>
  );
}

function Meters({ value, set }: { value: { km: string; h: string }; set: (v: { km: string; h: string }) => void }) {
  return (
    <>
      <label>
        Compteur kilométrique de l'engin
        <input type="number" step="0.1" min="0" value={value.km} onChange={(e) => set({ ...value, km: e.target.value })} />
      </label>
      <label>
        Compteur horaire de l'engin
        <input type="number" step="0.1" min="0" value={value.h} onChange={(e) => set({ ...value, h: e.target.value })} />
      </label>
    </>
  );
}

const meters = (m: { km: string; h: string }) => ({ odometer_km: orNull(m.km), hour_meter: orNull(m.h) });

function MountForm({ tyre, onCancel, onSubmit }: { tyre: Tyre; onCancel: () => void; onSubmit: (b: unknown) => Promise<unknown> }) {
  const vehicles = useQuery({
    queryKey: ["vehicles", "tyres", tyre.site_id],
    queryFn: () => read("/vehicles", { query: { site_id: tyre.site_id, page_size: 200 } }),
  });
  const [vehicle, setVehicle] = useState("");
  const [position, setPosition] = useState("");
  const [m, setM] = useState({ km: "", h: "" });
  return (
    <ActionForm title="Monter le pneu" submitLabel="Monter" onCancel={onCancel} onSubmit={() => onSubmit({ vehicle_id: vehicle, position_code: position.trim().toUpperCase(), ...meters(m) })}>
      <label>
        Engin
        <select required value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
          <option value="">— Choisir —</option>
          {(vehicles.data?.items ?? [])
            .filter((v) => v.status !== "RETIRED")
            .map((v) => (
              <option key={v.vehicle_id} value={v.vehicle_id}>
                {v.fleet_number}
              </option>
            ))}
        </select>
      </label>
      <label>
        Position (ex. AV-G, AR-D-EXT)
        <input required pattern="[A-Za-z0-9-]{1,16}" value={position} onChange={(e) => setPosition(e.target.value)} />
      </label>
      <Meters value={m} set={setM} />
      <p className="muted small">Au moins un compteur est exigé : il sert au calcul du coût au km ou à l'heure.</p>
    </ActionForm>
  );
}

function DismountForm({ onCancel, onSubmit }: { onCancel: () => void; onSubmit: (b: unknown) => Promise<unknown> }) {
  const [reason, setReason] = useState("WEAR");
  const [tread, setTread] = useState("");
  const [m, setM] = useState({ km: "", h: "" });
  return (
    <ActionForm title="Démonter le pneu" submitLabel="Démonter" onCancel={onCancel} onSubmit={() => onSubmit({ reason_code: reason, tread_mm: orNull(tread), ...meters(m) })}>
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          <Options map={TYRE_DISMOUNT_REASONS} />
        </select>
      </label>
      <Meters value={m} set={setM} />
      <label>
        Sculpture mesurée (mm, facultatif)
        <input type="number" step="0.1" min="0" value={tread} onChange={(e) => setTread(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function InspectForm({ mounted, onCancel, onSubmit }: { mounted: boolean; onCancel: () => void; onSubmit: (b: unknown) => Promise<unknown> }) {
  const [tread, setTread] = useState("");
  const [pressure, setPressure] = useState("");
  const [note, setNote] = useState("");
  const [m, setM] = useState({ km: "", h: "" });
  return (
    <ActionForm
      title="Contrôle d'usure"
      submitLabel="Enregistrer le contrôle"
      onCancel={onCancel}
      onSubmit={() =>
        onSubmit({ tread_mm: tread, pressure_kpa: pressure ? Number(pressure) : null, note: orNull(note), ...(mounted ? meters(m) : {}) })
      }
    >
      <label>
        Profondeur de sculpture (mm)
        <input required type="number" step="0.1" min="0" max="300" value={tread} onChange={(e) => setTread(e.target.value)} />
      </label>
      <label>
        Pression (kPa, facultatif)
        <input type="number" min="0" max="2000" value={pressure} onChange={(e) => setPressure(e.target.value)} />
      </label>
      {mounted && <Meters value={m} set={setM} />}
      <label>
        Observation (facultatif)
        <textarea maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
    </ActionForm>
  );
}

function ReturnForm({ tyre, onCancel, onSubmit }: { tyre: Tyre; onCancel: () => void; onSubmit: (b: unknown) => Promise<unknown> }) {
  const [action, setAction] = useState("REPAIRED");
  const [cost, setCost] = useState("");
  const [tread, setTread] = useState("");
  return (
    <ActionForm
      title="Retour de réparation"
      submitLabel="Enregistrer le retour"
      onCancel={onCancel}
      onSubmit={() =>
        onSubmit({
          action,
          cost: orNull(cost),
          currency: cost ? tyre.currency : null,
          new_tread_mm: action === "RETREADED" ? tread : null,
        })
      }
    >
      <label>
        Intervention
        <select value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="REPAIRED">Réparation</option>
          <option value="RETREADED">Rechapage</option>
        </select>
      </label>
      {action === "RETREADED" && (
        <label>
          Sculpture après rechapage (mm)
          <input required type="number" step="0.1" min="0.1" max="300" value={tread} onChange={(e) => setTread(e.target.value)} />
        </label>
      )}
      {tyre.currency ? (
        <label>
          Coût ({tyre.currency}, facultatif)
          <input type="number" step="0.01" min="0" value={cost} onChange={(e) => setCost(e.target.value)} />
        </label>
      ) : (
        <p className="muted small">Coût d'achat inconnu : le coût de l'intervention ne peut pas être agrégé.</p>
      )}
    </ActionForm>
  );
}

function ScrapForm({ onCancel, onSubmit }: { onCancel: () => void; onSubmit: (b: unknown) => Promise<unknown> }) {
  const [reason, setReason] = useState("WORN_OUT");
  const [tread, setTread] = useState("");
  return (
    <ActionForm title="Mettre au rebut" submitLabel="Mettre au rebut" danger onCancel={onCancel} onSubmit={() => onSubmit({ reason_code: reason, tread_mm: orNull(tread) })}>
      <label>
        Motif
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          <Options map={TYRE_SCRAP_REASONS} />
        </select>
      </label>
      <label>
        Sculpture finale (mm, facultatif)
        <input type="number" step="0.1" min="0" value={tread} onChange={(e) => setTread(e.target.value)} />
      </label>
    </ActionForm>
  );
}

/** Pneus actuellement montés sur un engin (fiche véhicule). */
export function VehicleTyres({ vehicleId, siteId }: { vehicleId: string; siteId: string }) {
  const me = useMe();
  const allowed = can(me.grants, "maintenance.tyre.read", siteId);
  const tyres = useQuery({
    queryKey: ["tyres", "vehicle", vehicleId],
    enabled: allowed,
    queryFn: () => read("/tyres", { query: { vehicle_id: vehicleId, status: "MOUNTED", page_size: 50 } }),
  });
  if (!allowed) return null;
  const items = [...(tyres.data?.items ?? [])].sort((a, b) => (a.position_code ?? "").localeCompare(b.position_code ?? ""));
  return (
    <section aria-label="Pneus montés">
      <h2>Pneus montés</h2>
      <DataState loading={tyres.isLoading} error={tyres.error} empty={items.length === 0} emptyText="Aucun pneu suivi monté sur cet engin.">
        <ul>
          {items.map((t) => (
            <li key={t.tyre_id}>
              <strong>{t.position_code}</strong> — <Link to={`/pneus/${t.tyre_id}`}>{t.brand} {t.serial_number}</Link> —{" "}
              {t.last_tread_mm != null ? `${number.format(Number(t.last_tread_mm))} mm` : "sculpture non mesurée"} <Alerts tyre={t} />
            </li>
          ))}
        </ul>
      </DataState>
    </section>
  );
}
