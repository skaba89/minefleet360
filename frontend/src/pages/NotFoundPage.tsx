import { Link } from "react-router";

/** Route attrape-tout (*) : adresse inconnue dans le shell authentifié. */
export function NotFoundPage() {
  return (
    <section>
      <h1>Page introuvable</h1>
      <p className="muted">
        Cette adresse ne correspond à aucune page de MINEFLEET 360. Le lien est peut-être obsolète ou
        l'adresse a été mal saisie. Vérifiez la saisie ou repartez de l'accueil.
      </p>
      <p>
        <Link to="/">Retour à l'accueil</Link>
      </p>
    </section>
  );
}
