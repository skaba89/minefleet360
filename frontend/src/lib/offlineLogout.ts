import { clearOfflineDrafts } from "./offlineDrafts";
import { purgeOutbox } from "./offline-outbox";

/** Purge les brouillons du compte et toute file outbox locale (appareil partagé). */
export async function purgeDraftsForSignedOutUser(profile: {
  workspace_code: string;
  user_account_id: string;
}): Promise<void> {
  // AllSettled garantit que la seconde purge est tentée même si la première échoue.
  const results = await Promise.allSettled([
    clearOfflineDrafts(`${profile.workspace_code}:${profile.user_account_id}`),
    purgeOutbox(),
  ]);
  if (results.some((result) => result.status === "rejected")) {
    throw new Error("La suppression des données locales n'a pas pu être confirmée");
  }
}
