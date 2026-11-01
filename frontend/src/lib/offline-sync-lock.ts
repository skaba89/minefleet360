/** Verrou navigateur exclusif : refus fermé si Web Locks est absent. */
import { identityKey, type OfflineIdentity } from "./offline-scope";

export interface LockManagerLike {
  request<T>(
    name: string,
    options: { mode: "exclusive"; ifAvailable: true },
    callback: (lock: { name: string } | null) => Promise<T>,
  ): Promise<T>;
}

/** Aucun fallback localStorage : il ne serait pas atomique entre onglets. */
export async function withExclusiveOfflineSync<T>(
  identity: OfflineIdentity,
  locks: LockManagerLike | null,
  work: () => Promise<T>,
): Promise<{ acquired: true; result: T } | { acquired: false }> {
  const scope = identityKey(identity);
  if (!locks) return { acquired: false };
  const name = `minefleet-offline-sync:${scope}`;
  return locks.request(name, { mode: "exclusive", ifAvailable: true }, async (lock) => {
    if (!lock) return { acquired: false };
    return { acquired: true, result: await work() };
  });
}
