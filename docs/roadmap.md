# Feuille de route

MintTweaks complète les outils de Linux Mint avec des actions compréhensibles,
des aperçus avant écriture, des sauvegardes et une logique système testable.
La séparation entre fonctions présentes et validation réelle s’applique à tous
les modules. Cette page regroupe les priorités ; les guides décrivent l’utilisation.

## Présent dans le code

- Neuf modules : accueil, entretien, services, Samba, Firefox, profils Cinnamon,
  parcours après installation, logiciels natifs et shells/terminaux.
- Simulation des commandes et des nettoyages Python ; instance de simulation
  distincte, aperçu complet et nouvelle vérification d’`autoremove`.
- Réservation commune des modifications, protection de fermeture et suivi des
  commandes administratives jusqu’à leur fin, même après dépassement de délai.
- Diagnostics distinguant résultat positif, anomalie et contrôle indisponible.
- Profils Cinnamon : sept réglages, capture, différences, application et restauration.
- Parcours facultatif de six étapes, incluant le terminal, avec notes et reprise.
- Helium et Brave depuis leurs sources APT officielles attendues, Zen depuis le
  paquet Debian non officiel du dépôt central ; sources préconfigurées requises.
- Catalogue de 32 outils de terminal ; intégrations Bash/Zsh/Fish, Kitty et
  Alacritty, réglages individuels, alias et export/import des choix personnels.
- Workflow de validation et de publication : préversions sur `main`, stables sur
  tag explicite ; l’exécution distante et les paquets doivent être vérifiés séparément.

## Priorité actuelle : valider sous Mint

La [recette](validation/linux-mint.md) et le [modèle de compte rendu](validation/compte-rendu.md)
sont prêts. Les essais réels n’ont pas encore été effectués.

- [ ] Construire et installer le `.deb` exact du candidat dans une VM Cinnamon.
- [ ] Vérifier les neuf pages, langues, thèmes, clavier et petites fenêtres.
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
- [ ] Exporter un diagnostic avec aperçu et masquage des informations personnelles.
- [ ] Conserver un historique structuré des opérations et de leurs résultats,
  avec restauration des configurations lorsque c’est possible.
- [ ] Définir un export des réglages des autres modules ; l’export personnel du
  terminal existe déjà et ne constitue pas une sauvegarde du système.
- [ ] Évaluer l’import de profils Cinnamon et le téléchargement facultatif de Nerd Fonts.

## Pistes à évaluer ensuite

| Domaine | Pistes conservées |
| --- | --- |
| Entretien | Gros fichiers, configurations résiduelles dpkg, entrées de menu cassées, nettoyage planifié |
| Services | Journal agrégé, messages du noyau, comparaison des démarrages et timers systemd |
| Partage | Export/import des partages Samba |
| Bureau | Applications par défaut et accès aux outils Mint existants |
| Système | Pare-feu ufw, permissions Flatpak, informations matérielles et batterie |
| Réglages avancés | sysctl dans un fichier dédié avec sauvegarde et restauration, à étudier plus tard |
| Parcours | Évaluer une vérification des résultats et une orchestration facultative ; le parcours actuel reste déclaratif |

## Décisions de périmètre

- Timeshift reste géré par son application Mint ; aucune intégration n’est prévue.
- Aucun profil prédéfini de terminal de type « Essentiel », « Développement » ou
  « Administration ». Les réglages et exports correspondent aux choix de l’utilisateur.
- Le module Logiciels natifs reste limité aux applications tierces natives ;
  aucun catalogue généraliste ni installation Flatpak dans ce module.
- Les dépôts et clés APT restent configurés avec les outils de Mint et les
  instructions des projets. Le dépôt APT central est maintenu séparément.
- Ne pas recréer les gestionnaires Mint de pilotes, mises à jour, PPA et miroirs.
  Les noyaux mainline, l’édition de fstab, GRUB et sudoers restent hors du périmètre.
