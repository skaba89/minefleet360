# MINEFLEET 360 — Claude Code starter kit

Ce kit contient les instructions, 8 agents, 8 skills, la vision métier, la roadmap et le prompt initial pour lancer un projet logiciel avec Claude Code. **Ce n'est pas encore une application fonctionnelle.**

## Démarrage
1. Extraire le ZIP dans un répertoire vide nommé `minefleet360` ou copier son contenu dans un dépôt Git existant après revue.
2. Ouvrir un terminal dans ce répertoire.
3. Exécuter `git init` (si nouveau dépôt), puis `claude` (Claude Code doit déjà être installé et authentifié).
4. Copier le contenu de `PROMPT_LANCEMENT_CLAUDE.md` dans Claude Code.
5. Examiner les plans et validations avant de passer aux développements.

Les agents sous `.claude/agents/*.md` peuvent être invoqués explicitement par leur nom. Les skills sous `.claude/skills/*/SKILL.md` sont découvrables par Claude Code selon la pertinence.

## Sécurité
Ne pas ajouter de secrets dans Git; vérifier tout code exécuté et toute demande de permission. Ne pas activer de bypass des permissions. Aucun environnement cloud n'est créé par ce kit.
