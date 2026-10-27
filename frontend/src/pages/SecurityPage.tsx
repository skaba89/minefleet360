import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { call, read, type Schemas } from "../api/client";
import { useAuth, useMe } from "../auth/AuthContext";
import { DataState } from "../components/common";
import { ActionForm } from "../components/forms";
import { formatDateTime } from "../lib/time";

/** Groupes de 4 caractères : saisie manuelle de la clé dans l'application d'authentification. */
function grouped(secret: string): string {
  return secret.match(/.{1,4}/g)?.join(" ") ?? secret;
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  return (
    <div className="card" role="region" aria-label="Codes de récupération">
      <h2>Vos codes de récupération</h2>
      <p>
        Chaque code permet <strong>une seule</strong> connexion si votre téléphone est perdu ou indisponible. Notez-les
        ou imprimez-les maintenant et rangez-les en lieu sûr : ils ne seront <strong>plus jamais affichés</strong>.
      </p>
      <ul className="codes">
        {codes.map((c) => (
          <li key={c}>
            <code>{c}</code>
          </li>
        ))}
      </ul>
      <div className="row">
        <button type="button" onClick={() => window.print()}>
          Imprimer
        </button>
        <button type="button" className="primary" onClick={onDone}>
          J'ai conservé mes codes
        </button>
      </div>
    </div>
  );
}

function Enroll({ onEnabled }: { onEnabled: (codes: string[]) => void }) {
  const [setup, setSetup] = useState<Schemas["MfaSetupOut"] | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  if (!setup) {
    return (
      <ActionForm
        title="Activer la double authentification"
        submitLabel="Commencer"
        onSubmit={async () => {
          const { data } = await call("post", "/me/mfa/setup", { body: { password } });
          setPassword("");
          setSetup(data);
        }}
      >
        <p>
          Installez une application d'authentification sur votre téléphone (par exemple Google Authenticator,
          Microsoft Authenticator ou FreeOTP), puis confirmez votre mot de passe. Elle fonctionne sans réseau.
        </p>
        <label>
          Mot de passe actuel
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
      </ActionForm>
    );
  }
  return (
    <ActionForm
      title="Associer votre téléphone"
      submitLabel="Activer"
      onSubmit={async () => onEnabled((await call("post", "/me/mfa/confirm", { body: { code } })).data.recovery_codes)}
    >
      <ol className="steps">
        <li>
          Dans l'application, choisissez « Ajouter un compte », puis « Saisir une clé de configuration » et entrez :
          <p className="secret">
            <code>{grouped(setup.secret)}</code>
          </p>
          (type : basé sur l'heure). Sur le téléphone lui-même, vous pouvez aussi{" "}
          <a href={setup.otpauth_uri}>ouvrir ce lien</a>.
        </li>
        <li>
          <label>
            Saisissez le code à 6 chiffres affiché par l'application
            <input
              required
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="[0-9 ]{6,7}"
              maxLength={7}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
        </li>
      </ol>
      <p className="muted small">La clé expire au bout de 15 minutes : recommencez si nécessaire.</p>
    </ActionForm>
  );
}

export function SecurityPage() {
  const me = useMe();
  const { refreshMe } = useAuth();
  const queryClient = useQueryClient();
  const [codes, setCodes] = useState<string[] | null>(null);
  const [panel, setPanel] = useState<"regenerate" | "disable" | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const status = useQuery({ queryKey: ["mfa-status"], queryFn: () => read("/me/mfa") });
  const refresh = async () => {
    setPanel(null);
    setCode("");
    setPassword("");
    await queryClient.invalidateQueries({ queryKey: ["mfa-status"] });
    await refreshMe();
  };
  const s = status.data;

  return (
    <section>
      <h1>Sécurité du compte</h1>
      {me.mfa_enrollment_required && !codes && (
        <p className="error" role="alert">
          Votre rôle exige la double authentification. Activez-la pour accéder à la plateforme.
        </p>
      )}
      {codes ? (
        <RecoveryCodes
          codes={codes}
          onDone={() => {
            setCodes(null);
            void refresh();
          }}
        />
      ) : (
        <DataState loading={status.isLoading} error={status.error} empty={!s}>
          {s && !s.enabled && <Enroll onEnabled={setCodes} />}
          {s?.enabled && (
            <>
              <p className="success" role="status">
                Double authentification active depuis le {formatDateTime(s.enabled_at, me.timezone)}.
              </p>
              <p>
                Codes de récupération restants : <strong>{s.recovery_codes_remaining}</strong>
                {s.recovery_codes_remaining <= 3 && " — pensez à en générer de nouveaux."}
              </p>
              <div className="toolbar">
                <button type="button" onClick={() => setPanel("regenerate")}>
                  Générer de nouveaux codes de récupération
                </button>
                {!s.required && (
                  <button type="button" onClick={() => setPanel("disable")}>
                    Désactiver
                  </button>
                )}
              </div>
              {panel === "regenerate" && (
                <ActionForm
                  title="Nouveaux codes de récupération"
                  submitLabel="Générer"
                  onCancel={() => setPanel(null)}
                  onSubmit={async () =>
                    setCodes((await call("post", "/me/mfa/recovery-codes", { body: { code } })).data.recovery_codes)
                  }
                >
                  <label>
                    Code actuel de l'application
                    <input required inputMode="numeric" maxLength={7} value={code} onChange={(e) => setCode(e.target.value)} />
                  </label>
                  <p className="muted small">Les anciens codes ne fonctionneront plus.</p>
                </ActionForm>
              )}
              {panel === "disable" && (
                <ActionForm
                  title="Désactiver la double authentification"
                  submitLabel="Désactiver"
                  danger
                  onCancel={() => setPanel(null)}
                  onDone={() => void refresh()}
                  onSubmit={() => call("post", "/me/mfa/disable", { body: { password, code } })}
                >
                  <label>
                    Mot de passe
                    <input
                      type="password"
                      required
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </label>
                  <label>
                    Code actuel de l'application
                    <input required inputMode="numeric" maxLength={7} value={code} onChange={(e) => setCode(e.target.value)} />
                  </label>
                </ActionForm>
              )}
            </>
          )}
        </DataState>
      )}
    </section>
  );
}
