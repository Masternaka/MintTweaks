# Compte rendu de validation MintTweaks

**État initial : non effectué.** Copier ce modèle avant de le remplir.

Recette suivie : [validation Linux Mint](linux-mint.md).

## Candidat et environnement

| Élément | Valeur |
| --- | --- |
| Date et personne ayant effectué les essais | À renseigner |
| Commit de base des sources | À renseigner |
| Modifications locales incluses | À renseigner |
| SHA-256 de l’archive transférée | À renseigner |
| Version et SHA-256 du `.deb` installé | À renseigner |
| Version exacte et édition de Linux Mint | À renseigner |
| Noyau et architecture | À renseigner |
| Version de Python et de Cinnamon | À renseigner |
| Session X11 ou Wayland | À renseigner |
| Hyperviseur et état initial de la VM | À renseigner |
| Langues et thèmes testés | À renseigner |

## Résultats

États autorisés : **non effectué**, **réussi**, **échoué**, **bloqué**, **sans objet**.
Pour « sans objet », expliquer pourquoi le scénario ne s’applique pas.

| Contrôle | État | Preuve, code de sortie ou anomalie |
| --- | --- | --- |
| Intégrité du transfert des sources | Non effectué | |
| Tests automatisés sous Linux, dont ordre des versions Debian | Non effectué | |
| `make check` | Non effectué | |
| Construction réelle du `.deb` | Non effectué | |
| Contenu et métadonnées du paquet | Non effectué | |
| Installation et import du paquet installé | Non effectué | |
| Vrai GTK, neuf pages, français et anglais | Non effectué | |
| Menu Cinnamon, clavier, thèmes clair et sombre | Non effectué | |
| Simulation CLI et variable d’environnement, témoins préservés | Non effectué | |
| Instance simulée distincte de l’instance normale | Non effectué | |
| Réservation entre pages, fermeture et Ctrl+Q | Non effectué | |
| Dépassement de délai administratif avec service temporaire | Non effectué | |
| M01 — Refus polkit | Non effectué | |
| M02 — Diagnostics Accueil | Non effectué | |
| M03 — Deux aperçus APT et annulation | Non effectué | |
| M04 — Suppression APT et plan modifié ou en échec | Non effectué | |
| M05 — Nettoyages réels de données de test | Non effectué | |
| M06 — Protection des noyaux | Non effectué | |
| M07 — Purge et redémarrage | Non effectué | |
| M08 — Journaux et démarrage | Non effectué | |
| M09 — Lecture impossible et données anciennes | Non effectué | |
| M10 — Installation Samba | Non effectué | |
| M11 — Partages Samba et sauvegardes | Non effectué | |
| M12 — Rejet et restauration Samba | Non effectué | |
| M13 — Comptes Samba et absence de secrets dans les journaux | Non effectué | |
| M14 — Installation Firefox après redémarrage | Non effectué | |
| M15 — Retrait de politique et préservation des autres réglages | Non effectué | |
| M16 — Désinstallation et réinstallation | Non effectué | |
| M17 — Application et restauration Cinnamon avec rendu réel | Non effectué | |
| M18 — Refus d’un aperçu Cinnamon périmé | Non effectué | |
| M19 — Récupération incomplète et sauvegardes conservées | Non effectué | |
| M20 — Assistant, récapitulatif et navigation | Non effectué | |
| M21 — Progression déclarée et reprise après réouverture | Non effectué | |
| M22 — Assistant en simulation et petite fenêtre | Non effectué | |
| M23 — Helium et Brave depuis leurs sources officielles | Non effectué | |
| M24 — Disponibilité du dépôt Zen et lancement réel | Non effectué | |
| M25 — Refus et échecs d’installation des logiciels | Non effectué | |
| M26 — Conservation des parcours au format 1 | Non effectué | |
| GitHub Actions et contrôle des pièces jointes distantes | Non effectué | Validation distincte |

## Anomalies

Pour chaque anomalie : scénario, étapes de reproduction, résultat attendu,
résultat observé, preuve, gravité et correction à vérifier. Ne pas inclure de
mot de passe ou de données personnelles dans les pièces jointes.

## Décision

- Résultat global : **non effectué**.
- Anomalies bloquantes : à renseigner.
- Scénarios non effectués ou sans objet et justification : à renseigner.
- Versions de Mint effectivement validées : aucune tant que la recette n’est pas exécutée.
- Nouveau candidat et scénarios à rejouer après correction : à renseigner.
- Publication : décision séparée, aucune autorisation donnée par ce compte rendu.

## Shells et terminaux

- T01–T12 : résultat, preuve ou raison de non-exécution pour chaque scénario.
- Versions de Kitty, Alacritty, Bash, Zsh, Fish et Starship :
- Format Alacritty réellement chargé (YAML/TOML) :
- Lancement depuis les deux entrées du menu Mint :
- Nouvelle session et restauration du shell de connexion :
- Activation/retrait Starship, conservation des alias :
- Restauration des fichiers, permissions et absence initiale :
- Aucun essai réel effectué : le préciser si ce rapport sert seulement de recette.

## Intégrations des outils

- U01–U05 et I01–I08 : résultats, preuves ou raisons de non-exécution.
- Shells et versions réellement essayés :
- fzf ancien/récent réellement chargé :
- Raccourcis, complétions, z/zi, alias bat/fd et pager delta :
- Suggestions/coloration Zsh et coexistence Atuin/fzf :
- Annulation de configuration après APT, retrait et restauration :

## Choix personnels du terminal

- P01–P09 : résultats, preuves ou raisons de non-exécution.
- États affichés comparés aux fichiers et au nouveau shell :
- Starship/fzf/bat, commandes mtk-eza/mtk-tmux et alias des trois shells :
- Export privé et import sur une autre machine ou dans un autre compte :
- Polices, formats Alacritty et chemins réellement vérifiés :
- Aucun profil prédéfini ajouté :
