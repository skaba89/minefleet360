import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState, ErrorMessage, Pager } from "../components/common";
import { EvidenceImage, EvidenceUploader } from "../components/Evidence";
import { ExportButton } from "../components/ExportButton";
import { downloadCsv, fetchAllPages, stamp, toCsv } from "../lib/csv";
import { ActionForm, Fact, Options, orNull } from "../components/forms";
import { HSE_ANSWER, HSE_RESULT, HSE_TARGET, label } from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime, utcToZonedInput, zonedInputToUtc } from "../lib/time";
import { useSites } from "../site/SiteContext";
import { ActionsTable, AddActionForm } from "./HsePages";

type Inspection = Schemas["InspectionOut"];
type Template = Schemas["TemplateOut"];
type Answer = Schemas["AnswerIn"];
const PAGE_SIZE = 50;

/** Inspections HSE (prise de poste, engins, zones de travail) et accès aux modèles de checklists. */
export function HseInspectionsPage() {
  const me = useMe();
  const { siteId, sites, timezoneOf } = useSites();
  const [result, setResult] = useState("");
  const [page, setPage] = useState(1);
  const [performing, setPerforming] = useState(false);
  const canRead = can(me.grants, "hse.inspection.read", siteId);
  const inspections = useQuery({
    queryKey: ["hse-inspections", siteId, result, page],
    enabled: canRead,
    queryFn: () =>
      read("/hse/inspections", {
        query: { site_id: siteId, result: (result || null) as Inspection["result"] | null, page, page_size: PAGE_SIZE },
      }),
  });
  const siteCode = new Map(sites.map((s) => [s.site_id, s.code]));
  const items = inspections.data?.items ?? [];
  return (
    <section>
      <Link className="back" to="/hse">
        ← Sécurité (HSE)
      </Link>
      <div className="page-head">
        <h1>Inspections</h1>
        <div className="row">
          {can(me.grants, "hse.checklist.manage") && <Link to="/hse/checklists">Modèles de checklists</Link>}
          {can(me.grants, "hse.inspection.perform", siteId) && !performing && (
            <button type="button" className="primary" onClick={() => setPerforming(true)}>
              Réaliser une inspection
            </button>
          )}
        </div>
      </div>
      {performing && <InspectionForm onClose={() => setPerforming(false)} />}
      {canRead ? (
        <>
          <div className="filters">
            <label>
              Résultat
              <select
                value={result}
                onChange={(e) => {
                  setResult(e.target.value);
                  setPage(1);
                }}
              >
                <Options map={HSE_RESULT} empty="Tous" />
              </select>
            </label>
            <ExportButton
              run={async () => {
                const { items, truncated } = await fetchAllPages((p, size) =>
                  read("/hse/inspections", {
                    query: { site_id: siteId, result: (result || null) as Inspection["result"] | null, page: p, page_size: size },
                  }),
                );
                downloadCsv(
                  `inspections-hse-${stamp()}.csv`,
                  toCsv(
                    ["Référence", "Site", "Réalisée le (UTC)", "Checklist", "Version", "Type", "Engin ou zone", "Inspecteur",
                      "Résultat", "Non-conformités", "Dont critiques", "Actions en cours"],
                    items.map((i) => [
                      i.reference, siteCode.get(i.site_id) ?? i.site_id, i.performed_at, i.template_name, i.template_version,
                      label(HSE_TARGET, i.target_type), i.vehicle_fleet_number ?? i.area_note ?? "", i.performed_by_name ?? "",
                      label(HSE_RESULT, i.result), i.nonconformities, i.critical_nonconformities, i.open_actions,
                    ]),
                  ),
                );
                return { truncated };
              }}
            />
          </div>
          <DataState loading={inspections.isLoading} error={inspections.error} empty={items.length === 0} emptyText="Aucune inspection.">
            <table>
              <thead>
                <tr>
                  <th scope="col">Inspection</th>
                  <th scope="col">Type</th>
                  <th scope="col">Objet</th>
                  <th scope="col">Non-conformités</th>
                  <th scope="col">Résultat</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.hse_inspection_id}>
                    <td>
                      <Link to={`/hse/inspections/${i.hse_inspection_id}`}>{i.reference}</Link> — {i.template_name}
                      <div className="small muted">
                        {siteCode.get(i.site_id)} — {formatDateTime(i.performed_at, timezoneOf(i.site_id))} — {i.performed_by_name}
                      </div>
                    </td>
                    <td>{label(HSE_TARGET, i.target_type)}</td>
                    <td>{i.vehicle_fleet_number ?? i.area_note ?? "—"}</td>
                    <td>
                      {i.nonconformities}
                      {i.critical_nonconformities > 0 && <div className="warn-text small">{i.critical_nonconformities} critique(s)</div>}
                      {i.open_actions > 0 && <div className="small muted">{i.open_actions} action(s) en cours</div>}
                    </td>
                    <td>
                      <Badge tone={i.result === "PASS" ? "ok" : "bad"}>{label(HSE_RESULT, i.result)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={page} pageSize={PAGE_SIZE} total={inspections.data?.total ?? 0} onPage={setPage} />
          </DataState>
        </>
      ) : (
        <p className="muted">Vous pouvez réaliser des inspections ; le registre est réservé aux responsables HSE et à l'encadrement.</p>
      )}
    </section>
  );
}

function InspectionForm({ onClose }: { onClose: () => void }) {
  const me = useMe();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { siteId, sites, timezoneOf } = useSites();
  const allowed = sites.filter((s) => can(me.grants, "hse.inspection.perform", s.site_id));
  const templates = useQuery({ queryKey: ["hse-templates"], queryFn: () => read("/hse/checklist-templates") });
  const [templateId, setTemplateId] = useState("");
  // Site calculé à chaque affichage : la liste des sites peut arriver après l'ouverture du formulaire.
  const [siteChoice, setSite] = useState("");
  const site = siteChoice || siteId || allowed[0]?.site_id || "";
  const [vehicle, setVehicle] = useState("");
  const [area, setArea] = useState("");
  const [note, setNote] = useState("");
  const [performedAt, setPerformedAt] = useState(utcToZonedInput(new Date(), timezoneOf(site)));
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [created, setCreated] = useState<Inspection | null>(null);
  const template = (templates.data ?? []).find((t) => t.hse_checklist_template_id === templateId);
  const vehicles = useQuery({
    queryKey: ["vehicles", "hse-inspection", site],
    enabled: !!site && can(me.grants, "fleet.vehicle.read", site) && template?.target_type !== "WORK_AREA",
    queryFn: () => read("/vehicles", { query: { site_id: site, page_size: 200 } }),
  });
  // Réponses initialisées au moment du choix de la checklist (et non dans un effet différé) : une saisie
  // rapide ne peut pas être écrasée, et chaque réponse porte toujours la clé de son point.
  const chooseTemplate = (id: string) => {
    setTemplateId(id);
    const chosen = (templates.data ?? []).find((t) => t.hse_checklist_template_id === id);
    setAnswers(Object.fromEntries((chosen?.items ?? []).map((i) => [i.key, { item_key: i.key, result: "COMPLIANT" as const }])));
  };
  const setAnswer = (key: string, patch: Partial<Answer>) =>
    setAnswers((current) => ({ ...current, [key]: { item_key: key, result: "COMPLIANT", ...current[key], ...patch } }));
  if (created) {
    return (
      <div className="card">
        <h2>
          Inspection {created.reference} enregistrée — {label(HSE_RESULT, created.result)}
        </h2>
        <EvidenceUploader uploadPath={`/hse/inspections/${created.hse_inspection_id}/evidence`} onUploaded={() => undefined} />
        <div className="row">
          {can(me.grants, "hse.inspection.read", created.site_id) && (
            <button type="button" className="primary" onClick={() => navigate(`/hse/inspections/${created.hse_inspection_id}`)}>
              Ouvrir l'inspection
            </button>
          )}
          <button type="button" onClick={onClose}>
            Terminer
          </button>
        </div>
      </div>
    );
  }
  return (
    <ActionForm
      title="Réaliser une inspection"
      submitLabel="Enregistrer l'inspection"
      onCancel={onClose}
      onSubmit={async () => {
        const { data } = await call("post", "/hse/inspections", {
          body: {
            site_id: site,
            hse_checklist_template_id: templateId,
            vehicle_id: vehicle || null,
            area_note: orNull(area),
            performed_at: zonedInputToUtc(performedAt, timezoneOf(site)).toISOString(),
            answers: Object.values(answers).map((a) => ({ ...a, comment: orNull(a.comment ?? "") })),
            note: orNull(note),
          },
        });
        void queryClient.invalidateQueries({ queryKey: ["hse-inspections"] });
        void queryClient.invalidateQueries({ queryKey: ["hse-summary"] });
        setCreated(data);
      }}
    >
      <label>
        Checklist
        <select required value={templateId} onChange={(e) => chooseTemplate(e.target.value)}>
          <option value="">— Choisir —</option>
          {(templates.data ?? []).map((t: Template) => (
            <option key={t.hse_checklist_template_id} value={t.hse_checklist_template_id}>
              {t.name} ({label(HSE_TARGET, t.target_type)}, v{t.version})
            </option>
          ))}
        </select>
      </label>
      <label>
        Site
        <select required value={site} onChange={(e) => setSite(e.target.value)}>
          <option value="">— Choisir —</option>
          {allowed.map((s) => (
            <option key={s.site_id} value={s.site_id}>
              {s.code} — {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Réalisée le (heure du site)
        <input type="datetime-local" required value={performedAt} onChange={(e) => setPerformedAt(e.target.value)} />
      </label>
      {template && template.target_type !== "WORK_AREA" && (
        <label>
          Engin{template.target_type === "VEHICLE" ? "" : " (facultatif)"}
          <select required={template.target_type === "VEHICLE"} value={vehicle} onChange={(e) => setVehicle(e.target.value)}>
            <option value="">— Choisir —</option>
            {(vehicles.data?.items ?? []).map((v) => (
              <option key={v.vehicle_id} value={v.vehicle_id}>
                {v.fleet_number}
              </option>
            ))}
          </select>
        </label>
      )}
      {template?.target_type === "WORK_AREA" && (
        <label>
          Zone inspectée
          <input required maxLength={200} value={area} onChange={(e) => setArea(e.target.value)} />
        </label>
      )}
      {template && (
        <fieldset className="checklist">
          <legend>Points de contrôle</legend>
          {template.items.map((item) => {
            const answer = answers[item.key];
            return (
              <div key={item.key} className="checklist-item">
                <p>
                  {item.label} {item.critical && <Badge tone="warn">Critique</Badge>}
                </p>
                <select
                  aria-label={`Résultat : ${item.label}`}
                  value={answer?.result ?? "COMPLIANT"}
                  onChange={(e) => setAnswer(item.key, { result: e.target.value as Answer["result"] })}
                >
                  <Options map={HSE_ANSWER} />
                </select>
                {answer?.result === "NON_COMPLIANT" && (
                  <input
                    required
                    aria-label={`Constat : ${item.label}`}
                    placeholder="Constat (obligatoire)"
                    maxLength={1000}
                    value={answer.comment ?? ""}
                    onChange={(e) => setAnswer(item.key, { comment: e.target.value })}
                  />
                )}
              </div>
            );
          })}
        </fieldset>
      )}
      <label>
        Observation générale (facultatif)
        <textarea maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <p className="muted small">Décrivez les constats sans nom de personne ; les photos s'ajoutent après l'enregistrement.</p>
    </ActionForm>
  );
}

/** Fiche d'inspection : réponses figées, photos, actions correctives sur les non-conformités. */
export function HseInspectionPage() {
  const { inspectionId = "" } = useParams();
  const me = useMe();
  const queryClient = useQueryClient();
  const { timezoneOf } = useSites();
  const [adding, setAdding] = useState(false);
  const inspection = useQuery({
    queryKey: ["hse-inspection", inspectionId],
    queryFn: () => call("get", "/hse/inspections/{hse_inspection_id}", { path: { hse_inspection_id: inspectionId } }),
  });
  const i = inspection.data?.data;
  const tz = timezoneOf(i?.site_id);
  const refresh = () => {
    setAdding(false);
    void queryClient.invalidateQueries({ queryKey: ["hse-inspection", inspectionId] });
    void queryClient.invalidateQueries({ queryKey: ["hse-actions"] });
  };
  const canManage = i ? can(me.grants, "hse.incident.manage", i.site_id) : false;
  return (
    <section>
      <Link className="back" to="/hse/inspections">
        ← Inspections
      </Link>
      <DataState loading={inspection.isLoading} error={inspection.error} empty={!i}>
        {i && (
          <>
            <div className="page-head">
              <h1>
                {i.reference} — {i.template_name} <Badge tone={i.result === "PASS" ? "ok" : "bad"}>{label(HSE_RESULT, i.result)}</Badge>
              </h1>
            </div>
            <dl className="facts">
              <Fact label="Type">{label(HSE_TARGET, i.target_type)}</Fact>
              <Fact label="Checklist">{`${i.template_code} v${i.template_version}`}</Fact>
              <Fact label="Engin">{i.vehicle_id ? <Link to={`/vehicules/${i.vehicle_id}`}>{i.vehicle_fleet_number}</Link> : null}</Fact>
              <Fact label="Zone">{i.area_note}</Fact>
              <Fact label="Réalisée le">{formatDateTime(i.performed_at, tz)}</Fact>
              <Fact label="Par">{i.performed_by_name}</Fact>
              <Fact label="Non-conformités">{`${i.nonconformities} dont ${i.critical_nonconformities} critique(s)`}</Fact>
              <Fact label="Observation">{i.note}</Fact>
            </dl>
            <h2>Points de contrôle</h2>
            <table>
              <thead>
                <tr>
                  <th scope="col">Point</th>
                  <th scope="col">Résultat</th>
                  <th scope="col">Constat</th>
                </tr>
              </thead>
              <tbody>
                {(i.answers ?? []).map((a) => (
                  <tr key={a.item_key}>
                    <td>
                      {a.label} {a.critical && <Badge tone="warn">Critique</Badge>}
                    </td>
                    <td>
                      <Badge tone={a.result === "NON_COMPLIANT" ? "bad" : a.result === "COMPLIANT" ? "ok" : "neutral"}>{label(HSE_ANSWER, a.result)}</Badge>
                    </td>
                    <td>{a.comment ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h2>Photos</h2>
            {(i.evidence ?? []).length === 0 && <p className="muted">Aucune photo.</p>}
            <div className="gallery">
              {(i.evidence ?? []).map((e, n) => (
                <figure key={e.hse_evidence_id}>
                  <EvidenceImage evidenceId={e.hse_evidence_id} alt={`Photo ${n + 1} de l'inspection ${i.reference}`} />
                  <figcaption className="small muted">{formatDateTime(e.uploaded_at, tz)}</figcaption>
                </figure>
              ))}
            </div>
            {can(me.grants, "hse.inspection.perform", i.site_id) && <EvidenceUploader uploadPath={`/hse/inspections/${i.hse_inspection_id}/evidence`} onUploaded={refresh} />}
            <h2>Actions correctives</h2>
            {canManage && i.nonconformities > 0 && !adding && (
              <button type="button" onClick={() => setAdding(true)}>
                Ajouter une action corrective
              </button>
            )}
            {adding && <AddActionForm parent={{ kind: "inspection", id: i.hse_inspection_id }} onCancel={() => setAdding(false)} onDone={refresh} />}
            <ActionsTable siteId={i.site_id} actions={i.actions ?? []} canManage={canManage} onChanged={refresh} />
          </>
        )}
      </DataState>
    </section>
  );
}

type ItemDraft = { key: string; label: string; critical: boolean };

/** Modèles de checklists (responsable HSE) : création d'une nouvelle version, désactivation. */
export function ChecklistTemplatesPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const templates = useQuery({
    queryKey: ["hse-templates", "all"],
    queryFn: () => read("/hse/checklist-templates", { query: { include_inactive: true } }),
  });
  const manage = can(me.grants, "hse.checklist.manage");
  const reload = () => {
    setCreating(false);
    void queryClient.invalidateQueries({ queryKey: ["hse-templates"] });
  };
  return (
    <section>
      <Link className="back" to="/hse/inspections">
        ← Inspections
      </Link>
      <div className="page-head">
        <h1>Modèles de checklists</h1>
        {manage && !creating && (
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            Nouveau modèle ou nouvelle version
          </button>
        )}
      </div>
      {creating && <TemplateForm onCancel={() => setCreating(false)} onDone={reload} />}
      {error !== null && <ErrorMessage error={error} />}
      <DataState loading={templates.isLoading} error={templates.error} empty={(templates.data ?? []).length === 0} emptyText="Aucun modèle.">
        <table>
          <thead>
            <tr>
              <th scope="col">Modèle</th>
              <th scope="col">Type</th>
              <th scope="col">Points</th>
              <th scope="col">État</th>
            </tr>
          </thead>
          <tbody>
            {(templates.data ?? []).map((t) => (
              <tr key={t.hse_checklist_template_id}>
                <td>
                  {t.name}
                  <div className="small muted">
                    {t.code} — version {t.version}
                  </div>
                </td>
                <td>{label(HSE_TARGET, t.target_type)}</td>
                <td>{t.items.length}</td>
                <td>
                  <Badge tone={t.active ? "ok" : "neutral"}>{t.active ? "En vigueur" : "Archivé"}</Badge>{" "}
                  {manage && t.active && (
                    <button
                      type="button"
                      onClick={() => {
                        setError(null);
                        call("post", "/hse/checklist-templates/{template_id}/deactivate", { path: { template_id: t.hse_checklist_template_id } })
                          .then(reload)
                          .catch(setError);
                      }}
                    >
                      Archiver
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DataState>
    </section>
  );
}

function TemplateForm({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("PRE_SHIFT");
  const [items, setItems] = useState<ItemDraft[]>([{ key: "", label: "", critical: false }]);
  const keyOf = (text: string, index: number) =>
    text
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 40) || `point_${index + 1}`;
  return (
    <ActionForm
      title="Modèle de checklist"
      submitLabel="Enregistrer la version"
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", "/hse/checklist-templates", {
          body: {
            code: code.trim(),
            name: name.trim(),
            target_type: target as Template["target_type"],
            items: items.map((item, index) => ({ key: `${keyOf(item.label, index)}_${index + 1}`, label: item.label.trim(), critical: item.critical })),
          },
        })
      }
    >
      <label>
        Code (une nouvelle version est créée si le code existe)
        <input required pattern="[A-Za-z0-9_-]{1,48}" value={code} onChange={(e) => setCode(e.target.value)} />
      </label>
      <label>
        Nom
        <input required minLength={3} maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Type d'inspection
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <Options map={HSE_TARGET} />
        </select>
      </label>
      <fieldset className="checklist">
        <legend>Points de contrôle</legend>
        {items.map((item, index) => (
          <div key={index} className="checklist-item">
            <input
              required
              aria-label={`Point ${index + 1}`}
              maxLength={300}
              value={item.label}
              onChange={(e) => setItems(items.map((it, n) => (n === index ? { ...it, label: e.target.value } : it)))}
            />
            <label className="checkbox">
              <input
                type="checkbox"
                checked={item.critical}
                onChange={(e) => setItems(items.map((it, n) => (n === index ? { ...it, critical: e.target.checked } : it)))}
              />
              Critique
            </label>
            {items.length > 1 && (
              <button type="button" onClick={() => setItems(items.filter((_, n) => n !== index))}>
                Retirer
              </button>
            )}
          </div>
        ))}
        {items.length < 100 && (
          <button type="button" onClick={() => setItems([...items, { key: "", label: "", critical: false }])}>
            Ajouter un point
          </button>
        )}
      </fieldset>
    </ActionForm>
  );
}
