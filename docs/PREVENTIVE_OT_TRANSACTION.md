# Raccordement maintenance préventive → ordre de travail : contrat de transaction

## État vérifié dans le code (28 octobre 2026)

- `persist_due` insère une échéance avec une contrainte d'unicité et exécute `commit()`.
- `create_work_order` crée un OT, son événement et son audit, puis exécute également `commit()`.
- `maintenance_due.work_order_id` permet de rattacher l'OT à une échéance, mais n'est pas rempli par le processus actuel.
- L'appel séquentiel direct de ces deux services **n'est pas atomique** : une panne entre les transactions peut créer des objets orphelins.

## Exigences avant activation automatique

1. Extraire un noyau de création d'OT **sans commit**, réutilisé par l'API corrective et par le planificateur.
2. Dans une transaction unique : verrouiller le plan / échéance, vérifier tenant + site, créer l'OT préventif, écrire l'événement et l'audit, lier l'OT à l'échéance, puis committer.
3. Respecter l'unicité `(tenant_id, work_order_id)` et la contrainte du lien échéance / OT. Vérifier la correspondance tenant **et véhicule** pour éviter de rattacher l'OT d'un autre engin.
4. Verrouiller explicitement le cycle de maintenance et interdire de créer plusieurs OT pour une même échéance.
5. Tester sur PostgreSQL : deux workers concurrents, rejeu, crash avant commit, reprise après crash, refus inter-tenant et hors site.
6. Traiter les changements métier : plan suspendu, véhicule retiré, compteur invalidé, OT rejeté / annulé, clôture avec nouveaux jalons.
7. Définir qui est le compte technique et les permissions minimales de l'exécuteur ; ne jamais contourner la RLS.
8. Prévoir une supervision des échecs et une stratégie de reprise sans production d'un nouvel OT en doublon.

**Statut :** revue de conception uniquement. Ne pas activer d'automatisation dans cette PR.
