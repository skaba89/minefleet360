/** Contrat de séparation d'une file locale sur terminal potentiellement partagé. */
export interface OfflineIdentity {
  tenantId: string;
  userId: string;
  siteId: string;
}

export function identityKey(identity: OfflineIdentity): string {
  const { tenantId, userId, siteId } = identity;
  if (!tenantId || !userId || !siteId) throw new Error("Identité terrain incomplète");
  return JSON.stringify([tenantId, userId, siteId]);
}

/** Une reconnexion ne doit jamais autoriser le rejeu sous une autre identité. */
export function mayResumeOfflineQueue(
  original: OfflineIdentity,
  current: OfflineIdentity | null,
): boolean {
  if (current === null) return false;
  try {
    return identityKey(original) === identityKey(current);
  } catch {
    return false;
  }
}
