import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage } from "../components/common";
import { ActionForm, Fact, Options, orNull } from "../components/forms";
import {
  ASSIGNMENT_STATUS,
  DOCUMENT_STATUS,
  DRIVER_STATUS,
  EMPLOYMENT,
  label,
  QUALIFICATION_TYPES,
  SUSPENSION_REASONS,
  UNAVAILABILITY_REASONS,
  VALIDITY,
  VALIDITY_TONE,
} from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDate, formatDateTime } from "../lib/time";
import { useSites } from "../site/SiteContext";
import { DRIVER_TONE, PHONE_PATTERN, type DriverStatusCode } from "./DriversPage";
import { useCategories } from "./VehiclesPage";

type Driver = Schemas["DriverOut"];
type License = Schemas["LicenseOut"];
type Qualification = Schemas["QualificationOut"];

// Catégories de permis du référentiel (valeurs fictives de développement, à valider localement : C-07).
const LICENSE_CATEGORIES: Record<string, string> = {
  A: "A — Motocyclettes",
  B: "B — Véhicules légers",
  C: "C — Poids lourds",
  D: "D — Transport de personnes",
  E: "E — Ensemble avec remorque",
};

type Panel = "edit" | "status" | "license" | "qualification" | null;

export function DriverDetailPage() {
  const { driverId = "" } = useParams();
  const location = useLocation();
  const me = useMe();
  const { sites, timezoneOf } = useSites();
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<Panel>(null);
  const driver = useQuery({
    queryKey: ["driver", driverId],
    queryFn: () => call("get", "/drivers/{driver_id}", { path: { driver_id: driverId } }),
  });
  const d = driver.data?.data;
  const etag = driver.data?.etag ?? null;
  const refresh = () => {
    setPanel(null);
    void queryClient.invalidateQueries({ queryKey: ["driver", driverId] });
    void queryClient.invalidateQueries({ queryKey: ["driver-docs", driverId] });
    void queryClient.invalidateQueries({ queryKey: ["drivers"] });
  };
  const possibleDuplicate = (location.state as { possibleDuplicate?: boolean } | null)?.possibleDuplicate;

  return (
    <section>
      <Link className="back" to="/conducteurs">
        ← Conducteurs
      </Link>
      <DataState loading={driver.isLoading} error={driver.error} empty={!d}>
        {d && (
          <>
            <div className="page-head">
              <h1>
                {d.last_name.toUpperCase()} {d.first_name}{" "}
                <Badge tone={DRIVER_TONE[d.status] ?? "neutral"}>{label(DRIVER_STATUS, d.status)}</Badge>
              </h1>
            </div>
            {possibleDuplicate && (
              <p className="warn-text" role="status">
                Un conducteur du même nom existe déjà sur ce site : vérifiez qu'il ne s'agit pas d'un doublon.
              </p>
            )}
            <div className="toolbar">
              {can(me.grants, "workforce.driver.update", d.site_id) && (
                <button type="button" onClick={() => setPanel("edit")}>
                  Modifier
                </button>
              )}
              {can(me.grants, "workforce.driver.deactivate", d.site_id) && (
                <button type="button" onClick={() => setPanel("status")}>
                  Changer le statut
                </button>
              )}
              {can(me.grants, "workforce.driver_license.manage", d.site_id) && (
                <button type="button" onClick={() => setPanel("license")}>
                  Ajouter un permis
                </button>
              )}
              {can(me.grants, "workforce.driver_qualification.manage", d.site_id) && (
                <button type="button" onClick={() => setPanel("qualification")}>
                  Ajouter une habilitation
                </button>
              )}
            </div>
            {panel === "edit" && <EditDriver driver={d} etag={etag} onDone={refresh} onCancel={() => setPanel(null)} />}
            {panel === "status" && (
              <ChangeDriverStatus driver={d} etag={etag} onDone={refresh} onCancel={() => setPanel(null)} />
            )}
            {panel === "license" && <AddLicense driver={d} onDone={refresh} onCancel={() => setPanel(null)} />}
            {panel === "qualification" && (
              <AddQualification driver={d} onDone={refresh} onCancel={() => setPanel(null)} />
            )}
            <dl className="facts">
              <Fact label="Matricule">{d.employee_number}</Fact>
              <Fact label="Site">{sites.find((s) => s.site_id === d.site_id)?.name}</Fact>
              {/* Champs RH masqués par le serveur pour les autres rôles (D-15) : absents de la réponse. */}
              {"phone" in d && <Fact label="Téléphone">{d.phone}</Fact>}
              {"employment_type" in d && <Fact label="Contrat">{label(EMPLOYMENT, d.employment_type)}</Fact>}
              {d.external_company_name && <Fact label="Entreprise">{d.external_company_name}</Fact>}
              {"hire_date" in d && <Fact label="Embauche">{formatDate(d.hire_date)}</Fact>}
              {d.exit_date && <Fact label="Sortie">{formatDate(d.exit_date)}</Fact>}
              {d.unavailability_reason && (
                <Fact label="Indisponibilité">
                  {label(UNAVAILABILITY_REASONS, d.unavailability_reason)}
                  {d.unavailable_until ? ` jusqu'au ${formatDate(d.unavailable_until)}` : ""}
                </Fact>
              )}
              {d.suspension_reason_code && (
                <Fact label="Motif de suspension">{label(SUSPENSION_REASONS, d.suspension_reason_code)}</Fact>
              )}
            </dl>
            <Documents driver={d} onChanged={refresh} />
            <DriverAssignments driver={d} timeZone={timezoneOf(d.site_id)} />
          </>
        )}
      </DataState>
    </section>
  );
}

interface PanelProps {
  driver: Driver;
  onDone: () => void;
  onCancel: () => void;
}

function EditDriver({ driver: d, etag, onDone, onCancel }: PanelProps & { etag: string | null }) {
  const me = useMe();
  const { sites } = useSites();
  const initial = {
    site_id: d.site_id,
    last_name: d.last_name,
    first_name: d.first_name,
    phone: d.phone ?? "",
    employment_type: d.employment_type ?? "",
    external_company_name: d.external_company_name ?? "",
    hire_date: d.hire_date ?? "",
  };
  const [form, setForm] = useState(initial);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const hrFields = "phone" in d; // seul un lecteur des champs RH peut les voir et donc les modifier

  return (
    <ActionForm
      title="Modifier le conducteur"
      submitLabel="Enregistrer"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() => {
        const body: Record<string, string | null> = {};
        for (const key of Object.keys(form) as (keyof typeof form)[]) {
          if (form[key] !== initial[key]) body[key] = key === "site_id" ? form[key] : orNull(form[key]);
        }
        return call("patch", "/drivers/{driver_id}", {
          path: { driver_id: d.driver_id },
          body: body as Schemas["DriverUpdate"],
          ifMatch: etag,
        });
      }}
    >
      <label>
        Site de rattachement
        <select value={form.site_id} onChange={set("site_id")}>
          {sites
            .filter((s) => s.site_id === d.site_id || (s.status === "ACTIVE" && can(me.grants, "workforce.driver.update", s.site_id)))
            .map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.code} — {s.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Nom
        <input required maxLength={80} value={form.last_name} onChange={set("last_name")} />
      </label>
      <label>
        Prénom
        <input required maxLength={80} value={form.first_name} onChange={set("first_name")} />
      </label>
      {hrFields && (
        <>
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
        </>
      )}
    </ActionForm>
  );
}

function ChangeDriverStatus({ driver: d, etag, onDone, onCancel }: PanelProps & { etag: string | null }) {
  const targets = (Object.keys(DRIVER_STATUS) as DriverStatusCode[]).filter((s) => s !== d.status);
  const [status, setStatus] = useState<DriverStatusCode>(targets[0] ?? "ACTIVE");
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const [exitDate, setExitDate] = useState("");
  return (
    <ActionForm
      title="Changer le statut du conducteur"
      submitLabel="Valider le statut"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/drivers/{driver_id}/status", {
          path: { driver_id: d.driver_id },
          ifMatch: etag,
          body: {
            status,
            unavailability_reason:
              status === "UNAVAILABLE" ? (reason as Schemas["DriverStatusChange"]["unavailability_reason"]) : null,
            unavailable_until: status === "UNAVAILABLE" ? orNull(until) : null,
            suspension_reason_code:
              status === "SUSPENDED" ? (reason as Schemas["DriverStatusChange"]["suspension_reason_code"]) : null,
            exit_date: status === "INACTIVE" ? orNull(exitDate) : null,
          },
        })
      }
    >
      <label>
        Nouveau statut
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as DriverStatusCode);
            setReason("");
          }}
        >
          {targets.map((t) => (
            <option key={t} value={t}>
              {label(DRIVER_STATUS, t)}
            </option>
          ))}
        </select>
      </label>
      {status === "UNAVAILABLE" && (
        <>
          <label>
            Motif
            <select required value={reason} onChange={(e) => setReason(e.target.value)}>
              <Options map={UNAVAILABILITY_REASONS} empty="— Choisir —" />
            </select>
          </label>
          <label>
            Jusqu'au (facultatif)
            <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
          </label>
        </>
      )}
      {status === "SUSPENDED" && (
        <label>
          Motif (codes uniquement, aucun motif médical)
          <select required value={reason} onChange={(e) => setReason(e.target.value)}>
            <Options map={SUSPENSION_REASONS} empty="— Choisir —" />
          </select>
        </label>
      )}
      {status === "INACTIVE" && (
        <label>
          Date de sortie
          <input type="date" required value={exitDate} onChange={(e) => setExitDate(e.target.value)} />
        </label>
      )}
      <p className="muted small">
        Un passage hors « Actif » est refusé tant qu'une affectation ouverte existe : clôturez-la d'abord.
      </p>
    </ActionForm>
  );
}

function AddLicense({ driver: d, onDone, onCancel }: PanelProps) {
  const [form, setForm] = useState({
    license_number: "",
    category_code: "C",
    issuing_authority: "",
    issue_date: "",
    expiry_date: "",
    document_reference: "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  return (
    <ActionForm
      title="Ajouter un permis"
      submitLabel="Enregistrer le permis"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/drivers/{driver_id}/licenses", {
          path: { driver_id: d.driver_id },
          body: {
            license_number: form.license_number.trim(),
            category_code: form.category_code,
            issuing_authority: orNull(form.issuing_authority),
            issue_date: form.issue_date,
            expiry_date: form.expiry_date,
            document_reference: orNull(form.document_reference),
          },
        })
      }
    >
      <label>
        N° de permis (visible des RH seulement)
        <input required minLength={3} maxLength={40} value={form.license_number} onChange={set("license_number")} />
      </label>
      <label>
        Catégorie
        <select value={form.category_code} onChange={set("category_code")}>
          <Options map={LICENSE_CATEGORIES} />
        </select>
      </label>
      <label>
        Autorité de délivrance
        <input maxLength={120} value={form.issuing_authority} onChange={set("issuing_authority")} />
      </label>
      <label>
        Délivré le
        <input type="date" required value={form.issue_date} onChange={set("issue_date")} />
      </label>
      <label>
        Expire le (inclus)
        <input type="date" required min={form.issue_date || undefined} value={form.expiry_date} onChange={set("expiry_date")} />
      </label>
      <label>
        Référence du justificatif
        <input maxLength={80} value={form.document_reference} onChange={set("document_reference")} />
      </label>
    </ActionForm>
  );
}

function AddQualification({ driver: d, onDone, onCancel }: PanelProps) {
  const categories = useCategories();
  const [form, setForm] = useState({
    qualification_type: "DRIVING_AUTHORIZATION",
    vehicle_category_id: "",
    site_only: false,
    valid_from: "",
    valid_to: "",
    reference: "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });
  const driving = form.qualification_type === "DRIVING_AUTHORIZATION";
  return (
    <ActionForm
      title="Ajouter une habilitation"
      submitLabel="Enregistrer l'habilitation"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/drivers/{driver_id}/qualifications", {
          path: { driver_id: d.driver_id },
          body: {
            qualification_type: form.qualification_type as Schemas["QualificationCreate"]["qualification_type"],
            vehicle_category_id: orNull(form.vehicle_category_id),
            site_id: form.site_only ? d.site_id : null,
            valid_from: form.valid_from,
            valid_to: orNull(form.valid_to),
            reference: orNull(form.reference),
          },
        })
      }
    >
      <label>
        Type
        <select value={form.qualification_type} onChange={set("qualification_type")}>
          <Options map={QUALIFICATION_TYPES} />
        </select>
      </label>
      <label>
        Catégorie d'engin{driving ? " (obligatoire)" : ""}
        <select required={driving} value={form.vehicle_category_id} onChange={set("vehicle_category_id")}>
          <option value="">—</option>
          {(categories.data ?? []).map((c) => (
            <option key={c.vehicle_category_id} value={c.vehicle_category_id}>
              {c.label_fr}
            </option>
          ))}
        </select>
      </label>
      <label>
        Valable à partir du
        <input type="date" required value={form.valid_from} onChange={set("valid_from")} />
      </label>
      <label>
        Jusqu'au (facultatif, inclus)
        <input type="date" min={form.valid_from || undefined} value={form.valid_to} onChange={set("valid_to")} />
      </label>
      <label>
        Référence (RH / HSE)
        <input maxLength={80} value={form.reference} onChange={set("reference")} />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.site_only}
          onChange={(e) => setForm({ ...form, site_only: e.target.checked })}
        />
        Limitée au site de rattachement
      </label>
    </ActionForm>
  );
}

function Documents({ driver: d, onChanged }: { driver: Driver; onChanged: () => void }) {
  const me = useMe();
  const categories = useCategories();
  const canLicenses = can(me.grants, "workforce.driver_license.read", d.site_id);
  const canQualifications = can(me.grants, "workforce.driver_qualification.read", d.site_id);
  const licenses = useQuery({
    queryKey: ["driver-docs", d.driver_id, "licenses"],
    enabled: canLicenses,
    queryFn: () => read("/drivers/{driver_id}/licenses", { path: { driver_id: d.driver_id } }),
  });
  const qualifications = useQuery({
    queryKey: ["driver-docs", d.driver_id, "qualifications"],
    enabled: canQualifications,
    queryFn: () => read("/drivers/{driver_id}/qualifications", { path: { driver_id: d.driver_id } }),
  });
  const categoryLabel = new Map((categories.data ?? []).map((c) => [c.vehicle_category_id, c.label_fr]));
  return (
    <>
      {canLicenses && (
        <>
          <h2>Permis</h2>
          <DataState
            loading={licenses.isLoading}
            error={licenses.error}
            empty={(licenses.data ?? []).length === 0}
            emptyText="Aucun permis enregistré."
          >
            <table>
              <thead>
                <tr>
                  <th scope="col">Catégorie</th>
                  <th scope="col">N°</th>
                  <th scope="col">Délivré</th>
                  <th scope="col">Expire</th>
                  <th scope="col">Validité</th>
                  {can(me.grants, "workforce.driver_license.manage", d.site_id) && <th scope="col">Statut</th>}
                </tr>
              </thead>
              <tbody>
                {(licenses.data ?? []).map((l) => (
                  <LicenseRow key={l.driver_license_id} license={l} driver={d} onChanged={onChanged} />
                ))}
              </tbody>
            </table>
          </DataState>
        </>
      )}
      {canQualifications && (
        <>
          <h2>Habilitations</h2>
          <DataState
            loading={qualifications.isLoading}
            error={qualifications.error}
            empty={(qualifications.data ?? []).length === 0}
            emptyText="Aucune habilitation enregistrée."
          >
            <table>
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col">Engin</th>
                  <th scope="col">Période</th>
                  <th scope="col">Validité</th>
                  {can(me.grants, "workforce.driver_qualification.revoke", d.site_id) && <th scope="col">Action</th>}
                </tr>
              </thead>
              <tbody>
                {(qualifications.data ?? []).map((q) => (
                  <QualificationRow
                    key={q.driver_qualification_id}
                    qualification={q}
                    driver={d}
                    categoryLabel={q.vehicle_category_id ? categoryLabel.get(q.vehicle_category_id) : undefined}
                    onChanged={onChanged}
                  />
                ))}
              </tbody>
            </table>
          </DataState>
        </>
      )}
    </>
  );
}

function LicenseRow({ license: l, driver: d, onChanged }: { license: License; driver: Driver; onChanged: () => void }) {
  const me = useMe();
  const canManage = can(me.grants, "workforce.driver_license.manage", d.site_id);
  const [status, setStatus] = useState(l.status);
  const [error, setError] = useState<unknown>(null);
  async function save(next: string) {
    setStatus(next);
    setError(null);
    try {
      await call("patch", "/driver-licenses/{license_id}", {
        path: { license_id: l.driver_license_id },
        body: { status: next as Schemas["LicenseUpdate"]["status"] },
        ifMatch: `"${l.row_version}"`,
      });
      onChanged();
    } catch (err) {
      setStatus(l.status);
      setError(err);
    }
  }
  return (
    <tr>
      <td>{l.category_code}</td>
      <td>{l.license_number ?? <span className="muted">masqué</span>}</td>
      <td>{formatDate(l.issue_date)}</td>
      <td>{formatDate(l.expiry_date)}</td>
      <td>
        <Badge tone={VALIDITY_TONE[l.validity] ?? "neutral"}>{label(VALIDITY, l.validity)}</Badge>
      </td>
      {canManage && (
        <td>
          <select aria-label="Statut du permis" value={status} onChange={(e) => void save(e.target.value)}>
            {["VALID", "SUSPENDED", "WITHDRAWN"].map((s) => (
              <option key={s} value={s}>
                {label(DOCUMENT_STATUS, s)}
              </option>
            ))}
          </select>
          {error !== null && <span className="error small"> Échec : rechargez la page.</span>}
        </td>
      )}
    </tr>
  );
}

function QualificationRow({
  qualification: q,
  driver: d,
  categoryLabel,
  onChanged,
}: {
  qualification: Qualification;
  driver: Driver;
  categoryLabel: string | undefined;
  onChanged: () => void;
}) {
  const me = useMe();
  const canRevoke = can(me.grants, "workforce.driver_qualification.revoke", d.site_id);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function revoke(status: "SUSPENDED" | "REVOKED") {
    setPending(true);
    setError(null);
    try {
      await call("post", "/driver-qualifications/{qualification_id}/revoke", {
        path: { qualification_id: q.driver_qualification_id },
        body: { status },
        ifMatch: `"${q.row_version}"`,
      });
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setPending(false);
    }
  }
  return (
    <tr>
      <td>{label(QUALIFICATION_TYPES, q.qualification_type)}</td>
      <td>{categoryLabel ?? "—"}</td>
      <td>
        {formatDate(q.valid_from)} → {q.valid_to ? formatDate(q.valid_to) : "sans échéance"}
      </td>
      <td>
        <Badge tone={VALIDITY_TONE[q.validity] ?? "neutral"}>{label(VALIDITY, q.validity)}</Badge>
      </td>
      {canRevoke && (
        <td className="actions">
          {q.status === "VALID" && (
            <>
              <button type="button" disabled={pending} onClick={() => void revoke("SUSPENDED")}>
                Suspendre
              </button>
              <button type="button" disabled={pending} onClick={() => void revoke("REVOKED")}>
                Révoquer
              </button>
            </>
          )}
          {error !== null && <ErrorMessage error={error} />}
        </td>
      )}
    </tr>
  );
}

function DriverAssignments({ driver: d, timeZone }: { driver: Driver; timeZone: string }) {
  const me = useMe();
  const allowed = can(me.grants, "assignment.vehicle_assignment.read", d.site_id);
  const assignments = useQuery({
    queryKey: ["driver-docs", d.driver_id, "assignments"],
    enabled: allowed,
    queryFn: () =>
      read("/drivers/{driver_id}/assignments", { path: { driver_id: d.driver_id }, query: { page_size: 20 } }),
  });
  if (!allowed) return null;
  return (
    <>
      <h2>Dernières affectations</h2>
      <DataState
        loading={assignments.isLoading}
        error={assignments.error}
        empty={(assignments.data?.items ?? []).length === 0}
        emptyText="Aucune affectation."
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Véhicule</th>
              <th scope="col">Début</th>
              <th scope="col">Fin</th>
              <th scope="col">Statut</th>
            </tr>
          </thead>
          <tbody>
            {(assignments.data?.items ?? []).map((a) => (
              <tr key={a.vehicle_assignment_id}>
                <td>
                  <Link to={`/vehicules/${a.vehicle_id}`}>{a.vehicle_fleet_number}</Link>
                </td>
                <td>{formatDateTime(a.valid_from, timeZone)}</td>
                <td>{formatDateTime(a.valid_to, timeZone)}</td>
                <td>{label(ASSIGNMENT_STATUS, a.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </>
  );
}
