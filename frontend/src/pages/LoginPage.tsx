import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router";

import { useAuth } from "../auth/AuthContext";
import { ErrorMessage } from "../components/common";

export function LoginPage() {
  const { status, login } = useAuth();
  const [workspace, setWorkspace] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(workspace, email, password);
    } catch (err) {
      setError(err);
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login">
      <form className="card" onSubmit={(e) => void submit(e)} aria-labelledby="login-title">
        <h1 id="login-title">MINEFLEET 360</h1>
        <p className="muted">Connexion à votre espace de travail</p>
        <label>
          Code de l'espace de travail
          <input
            name="workspace"
            autoComplete="organization"
            required
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
          />
        </label>
        <label>
          Adresse e-mail
          <input
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Mot de passe
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error !== null && <ErrorMessage error={error} />}
        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? "Connexion…" : "Se connecter"}
        </button>
        <Link to="/mot-de-passe-oublie">Mot de passe oublié ?</Link>
      </form>
    </main>
  );
}
