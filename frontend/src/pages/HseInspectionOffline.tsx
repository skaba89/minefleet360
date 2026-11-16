import { useState } from "react";

import { Badge } from "../components/common";
import { ActionForm, Options, orNull } from "../components/forms";
import { queueInspection, type Account, type InspectionDraft } from "../lib/hseOfflineSync";
import { HSE_ANSWER, HSE_TARGET, label } from "../lib/labels";
import type { InspectionKit } from "../lib/offlineInspectionKit";
import { utcToZonedInput, zonedInputToUtc } from "../lib/time";

type Answer = { item_key: string; result: "COMPLIANT" | "NON_COMPLIANT" | "NOT_APPLICABLE"; comment?: string | null };

/**
 * Inspection HSE réalisée application ouverte SANS réseau (phase 3, tranche 3), à partir du kit préparé en
 * ligne. Mêmes libellés et mêmes règles que le formulaire en ligne ; tout est revérifié par le serveur à la
 * synchronisation (modèle toujours actif, engin du site, permission). Les photos s'ajoutent ensuite, en ligne.
 */
export function QueueInspectionForm({
  account,
  kit,
  fallbackTimeZone,
  onQueued,
  onCancel,
}: {
  account: Account;
  kit: InspectionKit;
  fallbackTimeZone: string;
  onQueued: () => void;
  onCancel: () => void;
}) {
  const tzOf = (siteId: string) => kit.sites.find((s) => s.site_id === siteId)?.timezone ?? fallbackTimeZone;
  const [templateId, setTemplateId] = useState("");
  const [site, setSite] = useState(kit.sites[0]?.site_id ?? "");
  const [vehicle, setVehicle] = useState("");
  const [area, setArea] = useState("");
  const [note, setNote] = useState("");
  const [performedAt, setPerformedAt] = useState(() => utcToZonedInput(new Date(), tzOf(kit.sites[0]?.site_id ?? "")));
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const template = kit.templates.find((t) => t.hse_checklist_template_id === templateId);
  const siteVehicles = kit.vehicles.filter((v) => v.site_id === site);
  const chooseTemplate = (id: string) => {
    setTemplateId(id);
    const chosen = kit.templates.find((t) => t.hse_checklist_template_id === id);
    setAnswers(Object.fromEntries((chosen?.items ?? []).map((i) => [i.key, { item_key: i.key, result: "COMPLIANT" as const }])));
  };
  const setAnswer = (key: string, patch: Partial<Answer>) =>
    setAnswers((current) => ({ ...current, [key]: { item_key: key, result: "COMPLIANT", ...current[key], ...patch } }));
  return (
    <ActionForm
      title="Réaliser une inspection (hors ligne)"
      submitLabel="Enregistrer sur l'appareil"
      onCancel={onCancel}
      onSubmit={async () => {
        const body: InspectionDraft = {
          site_id: site,
          hse_checklist_template_id: templateId,
          vehicle_id: template?.target_type === "WORK_AREA" ? null : vehicle || null,
          area_note: template?.target_type === "WORK_AREA" ? orNull(area) : null,
          performed_at: zonedInputToUtc(performedAt, tzOf(site)).toISOString(),
          answers: Object.values(answers).map((a) => ({ ...a, comment: orNull(a.comment ?? "") })),
          note: orNull(note),
        };
        await queueInspection(account, body, template ? `${template.name} v${template.version}` : "");
        onQueued();
      }}
    >
      <label>
        Checklist
        <select required value={templateId} onChange={(e) => chooseTemplate(e.target.value)}>
          <option value="">— Choisir —</option>
          {kit.templates.map((t) => (
            <option key={t.hse_checklist_template_id} value={t.hse_checklist_template_id}>
              {t.name} ({label(HSE_TARGET, t.target_type)}, v{t.version})
            </option>
          ))}
        </select>
      </label>
      <label>
        Site
        <select
          required
          value={site}
          onChange={(e) => {
            setSite(e.target.value);
            setVehicle("");
          }}
        >
          {kit.sites.map((s) => (
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
            {siteVehicles.map((v) => (
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
      <p className="muted small">
        Checklists et engins préparés le {new Date(kit.saved_at).toLocaleDateString("fr-FR")} : le serveur revérifie tout à la
        synchronisation. Photos à ajouter ensuite, en ligne.
      </p>
    </ActionForm>
  );
}
