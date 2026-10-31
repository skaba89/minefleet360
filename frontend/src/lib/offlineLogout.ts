import { clearOfflineDrafts } from "./offlineDrafts";

/** Efface uniquement les brouillons liés au profil qui termine sa session. */
export async function purgeDraftsForSignedOutUser(profile: {
  workspace_code: string;
  user_account_id: string;
}): Promise<void> {
  await clearOfflineDrafts(`${profile.workspace_code}:${profile.user_account_id}`);
}
