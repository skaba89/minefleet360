# Livraison — récapitulatif HSE quotidien par e-mail

Branche `feature/hse-digest-notifications`, sans migration. Décision prise par délégation (voir
`docs/DECISIONS_DELEGUEES.md`, D-DEL-01), en réponse au point ouvert n° 3 de `MATRICE_RBAC.md` §6.

## Fonctionnement

`minefleet send-hse-digest [--dry-run]`, prévu une fois par jour (`infra/deploy/systemd/minefleet-hse-digest.*`,
06:30 heure du serveur), exécuté dans un conteneur éphémère de l'image API avec le **rôle applicatif** :

| Destinataire | Contenu |
|---|---|
| Responsable d'une action corrective ouverte en retard ou à échéance sous 2 jours (date du site) | référence de l'incident ou de l'inspection, échéance, « EN RETARD » / « à échéance proche » |
| Compte HSE actif | incidents **critiques ou élevés** non clôturés de sa portée (société ou site) |

- Un seul message par personne et par jour, **seulement s'il y a quelque chose à faire**.
- **Jamais** de titre, de description ni de nom : seulement des références, des gravités et des dates, plus le lien
  vers l'application (`MF_PUBLIC_WEB_URL`).
- Chaque envoi écrit un événement d'audit `hse.digest.sent` (acteur SYSTEM, nombre d'éléments).
- Une société en échec (base ou SMTP) n'empêche pas les suivantes ; son audit est annulé ; code de sortie 1.
- `--dry-run` compte les messages sans rien envoyer ni auditer.
- Canal : le port e-mail existant (`MF_MAIL_BACKEND=capture` en recette, `smtp` en production, cf. D-28).

## Vérifications

`tests/test_hse_digest.py` : destinataires exacts (responsables, HSE société, HSE de site limité à son site),
retard et échéance proche, action lointaine exclue, aucune donnée libre dans le corps, aucune autre société,
simulation sans envoi, audit, rien à envoyer quand rien n'est dû, échec SMTP signalé sans audit d'envoi.

## Activation (exploitation)

1. Configurer l'envoi réel (`MF_MAIL_BACKEND=smtp`, voir `DEPLOIEMENT_OVH.md`) et vérifier `MF_PUBLIC_WEB_URL`.
2. Lancer une fois `docker compose … run --rm api minefleet send-hse-digest --dry-run`.
3. Copier les deux fichiers systemd, adapter `WorkingDirectory`, puis `systemctl enable --now minefleet-hse-digest.timer`.

## Limites

Pas de préférences individuelles (désabonnement) ni d'autres sujets (pneus, carburant) : le panneau « À traiter »
de l'accueil les couvre dans l'application. Pas de SMS.
