# Feuille de route

MintTweaks complète les outils de Linux Mint avec des actions compréhensibles,
des aperçus avant écriture, des sauvegardes et une logique système testable.
La séparation entre fonctions présentes et validation réelle s’applique à tous
les modules. Cette page regroupe les priorités ; les guides décrivent l’utilisation.

## Présent dans le code

- Douze modules : accueil, entretien, services, Samba, Firefox, profils Cinnamon,
  parcours après installation, applications, logiciels natifs, shells/terminaux,
  dotfiles et historique des opérations.
- Simulation des commandes et des nettoyages Python ; instance de simulation
  distincte, aperçu complet et nouvelle vérification d’`autoremove`.
- Réservation commune des modifications, protection de fermeture et suivi des
  commandes administratives jusqu’à leur fin, même après dépassement de délai.
- Diagnostics distinguant résultat positif, anomalie et contrôle indisponible.
- Profils Cinnamon : sept réglages, capture, import/export JSON avec aperçu,
  différences, application et restauration.
- Parcours facultatif de six étapes, incluant le terminal, avec notes, reprise
  et observations locales sur demande, distinctes de la progression déclarée.
- Helium et Brave depuis leurs dépôts APT officiels avec configuration intégrée ;
  Zen depuis son installateur GitHub officiel, dans le dossier personnel.
- Volets d’information dans Applications et Logiciels natifs : méthode, portée,
  source attendue, version/révision et indications de mise à jour et de retrait.
- Catalogue de 32 outils de terminal ; intégrations Bash/Zsh/Fish, Kitty et
  Alacritty, réglages individuels, alias et export/import des choix personnels.
- Workflow de validation et de publication : préversions sur `main`, stables sur
  tag explicite ; l’exécution distante et les paquets doivent être vérifiés séparément.

## Priorité actuelle : valider sous Mint

La [recette](validation/linux-mint.md) et le [modèle de compte rendu](validation/compte-rendu.md)
sont prêts. Des essais ont déjà été réalisés par l’utilisateur sous Linux Mint ; leurs
résultats détaillés restent à consigner. Les nouvelles fonctions nécessitent
leurs propres vérifications dans une session Mint.

Commencer par la [checklist des nouveautés](validation/nouveautes.md), puis
compléter la recette globale pour le candidat destiné à la publication.

- [ ] Construire et installer le `.deb` exact du candidat dans une VM Cinnamon.
- [ ] Vérifier les douze pages, langues, thèmes, clavier et petites fenêtres.
- [ ] Tester les refus polkit, les erreurs APT, les conflits entre modules et la simulation.
- [ ] Vérifier nettoyages, protection des noyaux et sauvegardes/restaurations Samba.
- [ ] Vérifier les réglages Cinnamon et la conservation de la progression du parcours.
- [ ] Installer et lancer les trois navigateurs depuis leurs sources attendues.
- [ ] Charger les intégrations dans de nouveaux Bash/Zsh/Fish ; tester les alias,
  réglages et transferts entre comptes, y compris les formats Alacritty.
- [ ] Consigner les versions réellement testées et ajouter des captures représentatives.

## Prochains développements

- [ ] Étendre les aperçus aux autres suppressions et réduire les écarts entre
  simulation APT et exécution.
- [ ] Compléter le diagnostic Samba : services, configuration, permissions,
  pare-feu et accès local au partage, sans exposer les mots de passe.
- [x] Exporter un diagnostic local avec aperçu, exclusions des journaux bruts,
  masquage des identifiants courants et sauvegarde Markdown sans écrasement.
- [ ] Valider l’aperçu et la sélection du fichier de diagnostic sous Mint.
- [x] Conserver un historique structuré des opérations et de leurs résultats,
  avec références des sauvegardes et retour vers le module d’origine.
- [ ] Valider le rendu de l’historique et les restaurations existantes sous Mint.
- [x] Transférer une sélection du catalogue Applications par JSON avec aperçu,
  préparation des cases APT et conservation des choix indisponibles pour la session.
- [ ] Valider le transfert de sélections Applications entre machines Mint.
- [x] Transférer les références Dotfiles : URL GitHub, noms de configurations
  et option dotfiles, avec choix des chemins locaux et sans activation implicite.
- [ ] Valider les références Dotfiles entre deux machines Mint.
- [ ] Évaluer les transferts des autres modules ; les parcours existants restent
  distincts et ne constituent pas une sauvegarde du système.
- [x] Importer et exporter un profil Cinnamon avec aperçu, nouvelle identité locale
  et conservation des profils existants ; aucune application implicite.
- [ ] Valider les transferts Cinnamon entre deux machines Mint.
- [ ] Évaluer le téléchargement facultatif de Nerd Fonts.

## Pistes à évaluer ensuite

| Domaine | Pistes conservées |
| --- | --- |
| Entretien | Gros fichiers, configurations résiduelles dpkg, entrées de menu cassées, nettoyage planifié |
| Services | Journal agrégé, messages du noyau, comparaison des démarrages et timers systemd |
| Partage | Export/import des partages Samba |
| Bureau | Applications par défaut et accès aux outils Mint existants |
| Système | Pare-feu ufw, permissions Flatpak, informations matérielles et batterie |
| Réglages avancés | sysctl dans un fichier dédié avec sauvegarde et restauration, à étudier plus tard |
| Parcours | Étendre les observations pour des objectifs précisément définis ; évaluer une orchestration facultative, avec progression déclarative |

## Décisions de périmètre

- Timeshift reste géré par son application Mint ; aucune intégration n’est prévue.
- Aucun profil prédéfini de terminal de type « Essentiel », « Développement » ou
  « Administration ». Les réglages et exports correspondent aux choix de l’utilisateur.
- Le module Logiciels natifs reste limité aux applications tierces natives ;
  aucun catalogue généraliste ni installation Flatpak dans ce module.
- Le module Logiciels natifs peut configurer les sources fixes Helium et Brave
  ainsi que le dépôt Masternaka après confirmation. Les autres dépôts et clés
  restent gérés avec les outils de Mint et les instructions des projets.
  Le contenu du dépôt APT central est maintenu séparément.
- Ne pas recréer les gestionnaires Mint de pilotes, mises à jour, PPA et miroirs.
  Les noyaux mainline, l’édition de fstab, GRUB et sudoers restent hors du périmètre.
