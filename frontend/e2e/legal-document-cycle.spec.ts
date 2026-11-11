import { createHash } from "node:crypto";

import { expect, test } from "@playwright/test";

import { account, apiLogin, dispatcherSite, uiLogin } from "./fixtures";

// Écart n°1 de la recette UI P0 — cycle juridique documentaire complet sur serveur réel
// (dépôt -> vérification -> soumission -> décision -> réconciliation nominale), rendu possible
// par le harnais S3/ClamAV (scripts/dev/fake_s3.py + scripts/dev/fake_clamd.py) branché sur une
// API éphémère dédiée (MF_LEGAL_* + AWS_CA_BUNDLE). Sans ce harnais, l'API annonce SERVICE_BUSY
// (503) et le chemin dégradé est déjà couvert par e2e/costs-reconciliation.spec.ts.

/** PDF minimaliste (catalogue + 1 page, table xref correcte) accepté par inspect_contract_pdf. */
function buildPdf(comment?: string): Buffer {
  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
  ];
  const chunks: Buffer[] = [Buffer.from("%PDF-1.4\n", "latin1")];
  if (comment) chunks.push(Buffer.from(`% ${comment}\n`, "latin1"));
  const offsets: number[] = [];
  const lengthSoFar = () => chunks.reduce((total, chunk) => total + chunk.length, 0);
  objects.forEach((body, index) => {
    offsets.push(lengthSoFar());
    chunks.push(Buffer.from(`${index + 1} 0 obj\n${body}\nendobj\n`, "latin1"));
  });
  const xrefOffset = lengthSoFar();
  let xref = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) xref += `${offset.toString().padStart(10, "0")} 00000 n \n`;
  xref += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  chunks.push(Buffer.from(xref, "latin1"));
  return Buffer.concat(chunks);
}

// Signature de test EICAR (documentée publiquement ; le faux clamd la détecte et refuse).
const EICAR = "X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*";

test("cycle juridique documentaire complet : dépôt, scan, vérification, soumission, décision, réconciliation", async ({ page, request }) => {
  test.setTimeout(120_000);
  const admin = account("TENANT_ADMIN");
  const direction = account("DIRECTION", admin.workspace);
  const adminHeaders = await apiLogin(request, admin);
  const directionHeaders = await apiLogin(request, direction);
  const site = await dispatcherSite(request, await apiLogin(request, account("DISPATCHER", admin.workspace)));
  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
  const reference = `CTR-CYC-${suffix}`;

  const cleanPdf = buildPdf("Contrat E2E — document de test sans contenu réel");
  const infectedPdf = buildPdf(EICAR);
  const shaClean = createHash("sha256").update(cleanPdf).digest("hex");

  const sites = await (await request.get("/api/v1/sites", { headers: adminHeaders })).json();
  const siteInfo = sites.items.find((s: { site_id: string }) => s.site_id === site);
  expect(siteInfo, "site introuvable pour l'admin").toBeTruthy();

  // 1. Brouillon créé par l'API avec l'empreinte du justificatif qui sera déposé.
  const created = await request.post("/api/v1/legal-contracts", {
    headers: adminHeaders,
    data: {
      site_id: site,
      reference,
      title: `Contrat documentaire E2E ${suffix}`,
      counterparty_name: `Contrepartie E2E ${suffix}`,
      contract_type: "SUPPLIER",
      document_sha256: shaClean,
    },
  });
  expect(created.status()).toBe(201);
  const contract = await created.json();
  expect(contract.status).toBe("DRAFT");
  const contractId = contract.contract_id as string;

  // 2. Preflight : le dépôt est autorisé tant que le contrat reste en brouillon.
  const preflight = await request.post(`/api/v1/legal-contracts/${contractId}/documents/preflight`, { headers: adminHeaders });
  expect(preflight.status()).toBe(200);
  expect((await preflight.json()).allowed).toBe(true);

  // 3. Soumission sans preuve : refusée (le digest seul n'est pas une preuve de bytes sains).
  const earlySubmit = await request.post(`/api/v1/legal-contracts/${contractId}/submit`, { headers: adminHeaders });
  expect(earlySubmit.status()).toBe(409);

  // 4. Dépôt du justificatif sain : 201 PENDING (scan ClamAV + écriture S3 sur le harnais).
  const upload = await request.post(`/api/v1/legal-contracts/${contractId}/documents`, {
    headers: { ...adminHeaders, "Content-Type": "application/pdf", "X-Filename": `contrat-e2e-${suffix}.pdf` },
    data: cleanPdf,
  });
  expect(upload.status()).toBe(201);
  const document = await upload.json();
  expect(document.status).toBe("PENDING");
  const documentId = document.document_id as string;

  // 5. Dépôt d'un document infecté : refusé par le scan (ValueError -> 422), rien n'est stocké.
  const uploadInfected = await request.post(`/api/v1/legal-contracts/${contractId}/documents`, {
    headers: { ...adminHeaders, "Content-Type": "application/pdf", "X-Filename": `infecte-e2e-${suffix}.pdf` },
    data: infectedPdf,
  });
  expect(uploadInfected.status()).toBe(422);

  // 6. La soumission reste refusée tant que le document n'est que PENDING.
  const pendingSubmit = await request.post(`/api/v1/legal-contracts/${contractId}/submit`, { headers: adminHeaders });
  expect(pendingSubmit.status()).toBe(409);

  // 7. Vérification par la DIRECTION (legal.contract.review) : relecture S3 + re-scan -> VERIFIED.
  const verify = await request.post(`/api/v1/legal-contracts/${contractId}/documents/${documentId}/verify`, {
    headers: directionHeaders,
  });
  expect(verify.status()).toBe(200);
  expect((await verify.json()).status).toBe("VERIFIED");

  // 8. Re-vérification d'un document déjà VERIFIED : cachée (404), pas d'état intermédiaire exposé.
  const reverify = await request.post(`/api/v1/legal-contracts/${contractId}/documents/${documentId}/verify`, {
    headers: directionHeaders,
  });
  expect(reverify.status()).toBe(404);

  // 9. Soumission désormais prouvée : DRAFT -> PENDING_REVIEW.
  const submit = await request.post(`/api/v1/legal-contracts/${contractId}/submit`, { headers: adminHeaders });
  expect(submit.status()).toBe(200);
  expect((await submit.json()).status).toBe("PENDING_REVIEW");

  // 10. Réconciliation nominale : l'objet S3 existe et la ligne registre aussi -> cohérent.
  const reconciliation = await request.get("/api/v1/legal-contracts/storage-reconciliation", { headers: directionHeaders });
  expect(reconciliation.status()).toBe(200);
  expect(await reconciliation.json()).toEqual({ orphan_count: 0, missing_count: 0, consistent: true });

  // 11. Décision depuis l'UI (quatre-yeux : la DIRECTION n'a pas créé le contrat).
  await uiLogin(page, direction);
  await page.goto("/juridique");
  await page.getByRole("combobox", { name: "Site" }).selectOption({ label: `${siteInfo.code} — ${siteInfo.name}` });
  const draftRow = page.getByRole("row", { name: new RegExp(reference) });
  await expect(draftRow).toContainText("PENDING_REVIEW");
  await draftRow.getByRole("button", { name: "Examiner" }).click();
  await expect(page.getByText(`Contrat sélectionné : ${reference}`)).toBeVisible();
  await page.getByRole("combobox", { name: "Décision" }).selectOption("APPROVE");
  await page.getByRole("textbox", { name: "Motif de la décision" }).fill(`Justificatif vérifié par le harnais E2E ${suffix}.`);
  await page.getByRole("button", { name: "Confirmer la décision" }).click();
  await expect(page.getByText("Décision enregistrée. Elle ne constitue pas une signature électronique.")).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(reference) })).toContainText("APPROVED");

  // 12. Réconciliation depuis l'UI (panneau de la revue tenant) : cohérence annoncée.
  await page.getByRole("button", { name: "Contrôler le stockage" }).click();
  await expect(page.getByText("Aucune anomalie détectée.")).toBeVisible();
  await expect(page.getByText("Fichiers orphelins :")).toContainText("0");
  await expect(page.getByText("Fichiers manquants :")).toContainText("0");
});
