/**
 * Empreinte SHA-256 calculée au client (WebCrypto) — ex. justificatif de contrat juridique :
 * le navigateur calcule lui-même l'empreinte des octets choisis, avant tout envoi.
 */
export async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
