import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { request } from "../api/client";
import { ErrorMessage } from "../components/common";

const MIN_LENGTH = 12; // politique serveur (MF_PASSWORD_MIN_LENGTH), revérifiée côté API

/** Jeton porté par le fragment (#token=…) : jamais envoyé aux serveurs ni aux journaux, retiré de l'URL. */
function takeToken(): string {
  const match = /(?:^#|&)token=([^&]+)/.exec(window.location.hash);
  if (match) window.history.replaceState(null, "", window.location.pathname);
  return match ? decodeURIComponent(match[1]!) : "";
}

function SetPassword({ title, endpoint, done }: { title: string; endpoint: string; done: string }) {
  const [token] = useState(takeToken);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const mismatch = confirm.length > 0 && confirm !== password;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mismatch || password.length < MIN_LENGTH) return;
    setSubmitting(true);
    setError(null);
    try {
      await request(endpoint, { method: "POST", body: { token, password } });
      setSuccess(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login">
      <form className="card" onSubmit={(e) => void submit(e)} aria-labelledby="pw-title">
        <h1 id="pw-title">{title}</h1>
        {!token && !success && (
          <p className="error" role="alert">
            Lien incomplet : ouvrez le lien reçu par e-mail en entier, ou demandez-en un nouveau.
          </p>
        )}
        {success ? (
          <div className="success" role="status">
            <p>{done}</p>
            <Link to="/connexion">Se connecter</Link>
          </div>
        ) : (
          <>
            <label>
              Nouveau mot de passe ({MIN_LENGTH} caractères minimum)
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              Confirmer le mot de passe
              <input
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                aria-invalid={mismatch}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </label>
            {mismatch && <p className="error">Les deux mots de passe sont différents.</p>}
            {error !== null && <ErrorMessage error={error} />}
            <button type="submit" className="primary" disabled={submitting || !token || mismatch}>
              {submitting ? "Enregistrement…" : "Enregistrer"}
            </button>
          </>
        )}
      </form>
    </main>
  );
}

export function ActivationPage() {
  return (
    <SetPassword
      title="Activer votre compte"
      endpoint="/auth/invitations/accept"
      done="Votre compte est activé."
    />
  );
}

export function ResetConfirmPage() {
  return (
    <SetPassword
      title="Nouveau mot de passe"
      endpoint="/auth/password/reset-confirm"
      done="Votre mot de passe a été modifié. Toutes vos sessions ouvertes ont été fermées."
    />
  );
}

export function ResetRequestPage() {
  const [workspace, setWorkspace] = useState("");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await request("/auth/password/reset-request", {
        method: "POST",
        body: { workspace_code: workspace.trim(), email: email.trim() },
      });
      setSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login">
      <form className="card" onSubmit={(e) => void submit(e)} aria-labelledby="reset-title">
        <h1 id="reset-title">Mot de passe oublié</h1>
        {sent ? (
          // Réponse identique que le compte existe ou non (pas d'énumération).
          <div className="success" role="status">
            <p>Si un compte correspond, un lien de réinitialisation vient d'être envoyé.</p>
          </div>
        ) : (
          <>
            <label>
              Code de l'espace de travail
              <input required value={workspace} onChange={(e) => setWorkspace(e.target.value)} />
            </label>
            <label>
              Adresse e-mail
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            {error !== null && <ErrorMessage error={error} />}
            <button type="submit" className="primary" disabled={submitting}>
              Envoyer le lien
            </button>
          </>
        )}
        <Link to="/connexion">Retour à la connexion</Link>
      </form>
    </main>
  );
}
