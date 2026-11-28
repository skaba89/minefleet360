import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useMe } from "../auth/AuthContext";
import { Badge, DataState } from "../components/common";
import { ActionForm, Options } from "../components/forms";
import { MINING_DECISION, MINING_DECISION_TONE, MINING_STAGE, label } from "../lib/labels";
import { can } from "../lib/permissions";
import { formatDateTime } from "../lib/time";
import { useSites } from "../site/SiteContext";

type Revision = Schemas["ReadinessRevisionOut"];
type ReportSummary = Schemas["ReadinessReportSummaryOut"];
type ReviewHistory = Schemas["ReadinessReviewHistoryOut"];
type Stage = Schemas["ReadinessReviewCreate"]["stage"];

type Panel = { kind: "reject" | "approve"; report: ReportSummary } | null;

/**
 * Revue historique de préparation du réseau minier : rapports figés (preuves),
 * historique des décisions, rejet et approbation quatre-yeux. Ces écrans ne
 * décident jamais de l'autorisation opérationnelle en cours : celle-ci est
 * évaluée par le serveur au moment de chaque mission.
 */
export function MiningReadinessPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { siteId, timezoneOf } = useSites();
  const [revisionId, setRevisionId] = useState("");
  const [selected, setSelected] = useState("");
  const [panel, setPanel] = useState<Panel>(null);
  const readable = siteId !== null && can(me.grants, "dispatch.readiness.read", siteId);
  const revisions = useQuery({
    queryKey: ["mining-revisions", siteId],
    enabled: readable,
    queryFn: () => read("/sites/{site_id}/mining/revisions", { path: { site_id: siteId! } }),
  });
  // Sélection par défaut : la révision la plus récente, tant qu'elle reste listée.
  useEffect(() => {
    const items: Revision[] = revisions.data ?? [];
    if (items.length > 0 && !items.some((r) => r.revision_id === revisionId)) {
      setRevisionId(items[0]!.revision_id);
    }
  }, [revisions.data, revisionId]);
  const reports = useQuery({
    queryKey: ["readiness-reports", siteId, revisionId],
    enabled: readable && revisionId !== "",
    queryFn: () =>
      read("/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports", {
        path: { site_id: siteId!, revision_id: revisionId },
        query: { limit: 50 },
      }),
  });
  const tz = timezoneOf(siteId);
  const items = reports.data?.items ?? [];
  const refresh = () => {
    setPanel(null);
    void queryClient.invalidateQueries({ queryKey: ["readiness-reports"] });
    void queryClient.invalidateQueries({ queryKey: ["mining-revisions"] });
  };

  return (
    <section>
      <div className="page-head">
        <h1>Revue minière — préparation du réseau</h1>
      </div>
      <p className="muted small">
        Chaque relevé fige les preuves du réseau au moment de sa prise (empreinte, tolérance, anomalies). Une décision
        (rejet ou approbation) est motivée, datée et attribuée : l'étape technique est portée par l'exploitation, l'étape
        HSE par un second regard indépendant, et personne n'approuve son propre relevé. Ces archives ne valent jamais
        autorisation opérationnelle : le serveur réévalue l'état courant à chaque mission.
      </p>
      {siteId === null && (
        <p className="warn-text" role="note">
          Choisissez un site dans le sélecteur ci-dessus : la revue porte sur un site et un levé de réseau précis.
        </p>
      )}
      {siteId !== null && !can(me.grants, "dispatch.readiness.read", siteId) && (
        <p className="warn-text" role="note">
          Vous n'avez pas accès à la revue de préparation sur ce site.
        </p>
      )}
      {readable && (
        <>
          <div className="filters">
            <label>
              Levé de réseau
              <select value={revisionId} onChange={(e) => setRevisionId(e.target.value)}>
                {(revisions.data ?? []).map((r) => (
                  <option key={r.revision_id} value={r.revision_id}>
                    Version {r.version} — {new Date(r.created_at).toLocaleDateString("fr-FR")} —{" "}
                    {r.report_count} rapport(s)
                  </option>
                ))}
              </select>
            </label>
          </div>
          <DataState
            loading={reports.isLoading}
            error={reports.error}
            empty={items.length === 0}
            emptyText="Aucun relevé enregistré pour ce levé : ils sont créés à chaque prise de preuves du réseau."
          >
            <table>
              <thead>
                <tr>
                  <th scope="col">Pris le</th>
                  <th scope="col">Tolérance</th>
                  <th scope="col">Anomalies</th>
                  <th scope="col">Empreinte des preuves</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.report_id}>
                    <td>{formatDateTime(r.created_at, tz)}</td>
                    <td>{r.tolerance_m.toFixed(2)} m</td>
                    <td>
                      {r.finding_count === 0 ? (
                        <Badge tone="ok">Aucune</Badge>
                      ) : (
                        <Badge tone="bad">{r.finding_count}</Badge>
                      )}
                    </td>
                    <td className="small muted">
                      <code>{r.evidence_digest.slice(0, 16)}…</code>
                    </td>
                    <td>
                      <div className="row">
                        <button type="button" onClick={() => setSelected(r.report_id)}>
                          Examiner
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataState>
        </>
      )}
      {panel !== null && (
        <DecisionForm
          panel={panel}
          siteId={siteId!}
          revisionId={revisionId}
          tz={tz}
          onCancel={() => setPanel(null)}
          onDone={refresh}
        />
      )}
      {readable && selected !== "" && (
        <ReportExamination
          siteId={siteId!}
          revisionId={revisionId}
          reportId={selected}
          tz={tz}
          onClose={() => setSelected("")}
          onDecide={(kind) => {
            const report = items.find((r) => r.report_id === selected);
            if (report) setPanel({ kind, report });
          }}
        />
      )}
    </section>
  );
}

/** Fiche du relevé : preuves, anomalies et historique des décisions. */
function ReportExamination({
  siteId,
  revisionId,
  reportId,
  tz,
  onClose,
  onDecide,
}: {
  siteId: string;
  revisionId: string;
  reportId: string;
  tz: string;
  onClose: () => void;
  onDecide: (kind: "reject" | "approve") => void;
}) {
  const me = useMe();
  const detail = useQuery({
    queryKey: ["readiness-report", siteId, revisionId, reportId],
    queryFn: () =>
      read("/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}", {
        path: { site_id: siteId, revision_id: revisionId, report_id: reportId },
      }),
  });
  const review = useQuery({
    queryKey: ["readiness-review", siteId, revisionId, reportId],
    queryFn: () =>
      read("/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}/review", {
        path: { site_id: siteId, revision_id: revisionId, report_id: reportId },
      }),
  });
  const history: ReviewHistory | undefined = review.data;
  const decidedStages = new Set((history?.decisions ?? []).map((d) => d.stage));
  return (
    <div className="card">
      <div className="page-head">
        <h2>Relevé sélectionné</h2>
        <button type="button" onClick={onClose}>
          Fermer
        </button>
      </div>
      <DataState loading={detail.isLoading} error={detail.error} empty={false}>
        <dl>
          <dt>Empreinte complète</dt>
          <dd>
            <code>{detail.data?.summary.evidence_digest}</code>
          </dd>
          <dt>Tolérance appliquée</dt>
          <dd>{detail.data?.summary.tolerance_m.toFixed(2)} m</dd>
          <dt>Qualification du levé liée</dt>
          <dd>
            {detail.data?.summary.tolerance_qualification_id ? (
              <code>{detail.data.summary.tolerance_qualification_id}</code>
            ) : (
              "—"
            )}
          </dd>
        </dl>
        <h3>Anomalies figées ({detail.data?.findings.length ?? 0})</h3>
        {(detail.data?.findings.length ?? 0) === 0 ? (
          <p className="muted small">Aucune anomalie à cette tolérance : le graphe satisfait toutes les règles.</p>
        ) : (
          <ul>
            {(detail.data?.findings ?? []).map((f, index) => (
              <li key={`${f.code}-${f.segment_id ?? "none"}-${index}`}>
                <code>{f.code}</code>
                {f.segment_id && <span className="small muted"> — segment {f.segment_id.slice(0, 8)}…</span>}
              </li>
            ))}
          </ul>
        )}
        <h3>Historique des décisions</h3>
        {(history?.decisions.length ?? 0) === 0 ? (
          <p className="muted small">Aucune décision enregistrée pour ce relevé.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Étape</th>
                <th scope="col">Décision</th>
                <th scope="col">Motif</th>
                <th scope="col">Décidée le</th>
              </tr>
            </thead>
            <tbody>
              {(history?.decisions ?? []).map((d) => (
                <tr key={d.decision_id}>
                  <td>{label(MINING_STAGE, d.stage)}</td>
                  <td>
                    <Badge tone={MINING_DECISION_TONE[d.decision] ?? "neutral"}>
                      {label(MINING_DECISION, d.decision)}
                    </Badge>
                  </td>
                  <td>{d.reason}</td>
                  <td>{formatDateTime(d.created_at, tz)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="row">
          {can(me.grants, "dispatch.readiness.reject", siteId) && (
            <button type="button" onClick={() => onDecide("reject")}>
              Rejeter ce relevé
            </button>
          )}
          {can(me.grants, "dispatch.readiness.approve", siteId) && (
            <button type="button" onClick={() => onDecide("approve")}>
              Approuver ce relevé
            </button>
          )}
        </div>
        {(decidedStages.has("TECHNICAL") || decidedStages.has("HSE")) && (
          <p className="muted small">
            Chaque étape ne peut être décidée qu'une fois ; la seconde étape exige un rôle différent du premier décideur.
          </p>
        )}
      </DataState>
    </div>
  );
}

/** Rejet ou approbation motivés : le serveur revérifie le rôle de l'étape et les quatre yeux. */
function DecisionForm({
  panel,
  siteId,
  revisionId,
  tz,
  onCancel,
  onDone,
}: {
  panel: { kind: "reject" | "approve"; report: ReportSummary };
  siteId: string;
  revisionId: string;
  tz: string;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [stage, setStage] = useState<Stage>("TECHNICAL");
  const [reason, setReason] = useState("");
  const action = panel.kind === "reject" ? "reject" : "approve";
  const template = `/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}/${action}` as const;
  return (
    <ActionForm
      title={
        panel.kind === "reject"
          ? `Rejeter le relevé du ${formatDateTime(panel.report.created_at, tz)}`
          : `Approuver le relevé du ${formatDateTime(panel.report.created_at, tz)}`
      }
      submitLabel={panel.kind === "reject" ? "Rejeter" : "Approuver"}
      danger={panel.kind === "reject"}
      onCancel={onCancel}
      onDone={onDone}
      onSubmit={() =>
        call("post", template, {
          path: {
            site_id: siteId,
            revision_id: revisionId,
            report_id: panel.report.report_id,
          },
          body: { stage, reason: reason.trim() },
        })
      }
    >
      <label>
        Étape
        <select value={stage} onChange={(e) => setStage(e.target.value as Stage)}>
          <Options map={MINING_STAGE} />
        </select>
      </label>
      <label>
        Motif (obligatoire, 500 caractères au plus)
        <textarea
          required
          maxLength={500}
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Ce que la relecture des preuves a établi."
        />
      </label>
      <p className="muted small">
        Le serveur vérifie que votre rôle correspond à l'étape choisie, que la qualification du levé est toujours
        approuvée et que les preuves n'ont pas changé depuis la prise du relevé ; l'auteur d'un relevé ne peut pas
        l'approuver.
      </p>
    </ActionForm>
  );
}
