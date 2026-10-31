# Valorisation des stocks — migration 0040

Cette migration introduit des colonnes financières **facultatives** sans modifier les transactions existantes.

- `spare_part_balance.stock_value` : valeur historique du stock dans `valuation_currency`.
- `spare_part_movement.unit_cost` et `total_cost` : coût historisé par mouvement.
- `NULL` signifie **non valorisé**, en particulier pour tous les stocks antérieurs à 0040.
- Une valeur `0` constitue un coût connu nul : ne pas la confondre avec `NULL`.
- Les contraintes exigent que montant et devise soient renseignés ensemble.

## Limites délibérées

Aucune API ne renseigne encore ces champs. Les anciennes réceptions et sorties continuent de fonctionner
et ne constituent **pas** des mouvements valorisés. Les tableaux de bord financiers ne doivent pas
additionner des valeurs partielles ou substituer zéro à `NULL`.

## Lots obligatoires suivants

1. Valider méthode de valorisation, devise par tenant/site, valeur d'ouverture et règles d'arrondi.
2. Effectuer une initialisation contrôlée des stocks historiques sous approbation métier.
3. Rendre réceptions et sorties physico-financières atomiques (même transaction et verrou de solde).
4. Traiter les réservations consommées et rattacher explicitement les valeurs aux OT.
5. Ajouter des tests concurrents PostgreSQL : soldes physiques et valeurs inchangés lors des erreurs.
6. Exposer les coûts uniquement aux rôles habilités; ajouter rapprochement comptable et audit.

**Aucun GO production** ne peut reposer sur cette migration seule.
