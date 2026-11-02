import { clearOfflineDrafts } from "./offlineDrafts";
import { clearFieldProfile } from "./offlineFieldProfile";
import { purgeOutbox, purgeOutboxKeepingPending } from "./offline-outbox";

type Profile = { workspace_code: string; user_account_id: string };

/** Purge les brouillons du compte et toute file outbox locale (appareil partagé). */
export async function purgeDraftsForSignedOutUser(profile: Profile): Promise<void> {
  clearFieldProfile();
  // AllSettled garantit que la seconde purge est tentée même si la première échoue.
  const results = await Promise.allSettled([
    clearOfflineDrafts(`${profile.workspace_code}:${profile.user_account_id}`),
    purgeOutbox(),
  ]);
  if (results.some((result) => result.status === "rejected")) {
    throw new Error("La suppression des données locales n'a pas pu être confirmée");
  }
}

/**
 * Expiration de session (non choisie par l'utilisateur) : brouillons purgés, mais les déclarations terrain
 * en attente de CE compte sont conservées pour être synchronisées après sa reconnexion. Elles ne
 * contiennent aucun jeton et ne peuvent être rejouées que sous la même identité.
 */
export async function purgeAfterSessionExpiry(profile: Profile): Promise<void> {
  const results = await Promise.allSettled([
    clearOfflineDrafts(`${profile.workspace_code}:${profile.user_account_id}`),
    purgeOutboxKeepingPending({ tenantId: profile.workspace_code, userId: profile.user_account_id }),
  ]);
  if (results.some((result) => result.status === "rejected")) {
    throw new Error("La suppression des données locales n'a pas pu être confirmée");
  }
}
