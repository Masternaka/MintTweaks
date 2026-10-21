# MintTweaks — Vision et feuille de route

> Document de cadrage — 21 octobre 2026  
> Les fonctionnalités proposées ci-dessous constituent une direction de développement. Elles ne sont pas toutes disponibles dans l’application.

## Objectif du projet

MintTweaks vise à devenir un centre de réglages, de personnalisation et d’entretien pour Linux Mint, inspiré du fonctionnement d’[ArchLinux Tweak Tool](https://github.com/kirodubes/archlinux-tweak-tool).

L’objectif est de reprendre son principe : regrouper dans une interface graphique des opérations utiles qui nécessitent autrement plusieurs outils ou des commandes dans le terminal.

MintTweaks proposera une sélection de fonctionnalités adaptées à Linux Mint. La reproduction de toutes les fonctions d’ArchLinux Tweak Tool ne fait pas partie de l’objectif.

Dépôt du projet : [Masternaka/MintTweaks](https://github.com/Masternaka/MintTweaks).

## Principes de développement

- **Adapter les fonctions à Linux Mint.** Chaque module doit répondre à un besoin concret dans cet environnement.
- **Garder un périmètre maîtrisable.** Privilégier quelques modules utiles et fiables, puis élargir progressivement.
- **Faciliter la compréhension.** Expliquer ce qu’une action change et ses conséquences avant son exécution.
- **Permettre le retour en arrière lorsque c’est possible.** Sauvegarder les configurations et proposer leur restauration.
- **Compléter les outils existants.** Les intégrer ou proposer des raccourcis lorsqu’une nouvelle implémentation apporte peu de valeur.
- **Conserver une architecture modulaire.** Séparer la logique système de l’interface graphique afin de faciliter les tests et la maintenance.

## Base actuelle

Le projet dispose déjà de trois modules :

| Module | Fonctions principales |
| --- | --- |
| Entretien | Analyse de l’espace occupé, nettoyage, paquets orphelins et suppression d’anciens noyaux |
| Services | Gestion des services systemd, consultation des journaux et analyse du démarrage |
| Samba | Gestion des partages et des comptes, édition et validation de la configuration, sauvegardes et restauration |

Cette base donne surtout à l’application un rôle d’administration système. Les prochains modules doivent aussi développer la préparation et la personnalisation de Linux Mint.

La présence d’une fonction dans le code ne signifie pas que son comportement a été validé dans tous les environnements pris en charge.

## Périmètre proposé

| Section | Contenu proposé | État ou priorité |
| --- | --- | --- |
| Accueil | Résumé du système, diagnostics simples et accès aux outils | À développer en priorité |
| Entretien | Nettoyage, espace récupérable et aperçu des suppressions | Présent, à fiabiliser |
| Services | Gestion systemd, journaux et analyse du démarrage | Présent |
| Réseau et partage | Samba, état du réseau et diagnostics de connexion | Samba présent ; compléments à prévoir |
| Logiciels | Sélection d’applications, installation APT ou Flatpak et indication de l’état installé | Priorité haute |
| Terminal et shells | Installation de Bash, Zsh et Fish, choix du shell, Starship et polices Nerd Fonts | Priorité moyenne |
| Personnalisation | Profils coordonnés de thèmes, icônes, curseurs et polices | Priorité moyenne |
| Sauvegarde des réglages | Export et restauration des réglages gérés par MintTweaks | À envisager plus tard |

Ces sections constituent une proposition de périmètre, à ajuster selon les besoins et les résultats des essais.

## Fonctions à développer

### Accueil

Créer une page d’entrée qui permet de comprendre rapidement l’état du système et d’accéder aux fonctions principales.

Contenu envisagé :

- informations essentielles sur le système ;
- résumé des diagnostics ;
- accès aux modules de MintTweaks ;
- raccourcis vers les outils utiles de Linux Mint.

Les premiers diagnostics devraient fonctionner en lecture seule. Une anomalie détectée doit être expliquée avant de proposer une correction.

### Logiciels

Créer une sélection organisée d’applications pour faciliter la préparation d’une nouvelle installation.

Catégories envisagées :

- développement ;
- multimédia ;
- création graphique ;
- utilitaires.

Pour chaque application, afficher une courte description, son état d’installation et la source utilisée. Lorsque plusieurs sources sont proposées, préciser le choix entre APT et Flatpak.

La première version peut se limiter à un petit catalogue maintenu et vérifié.

### Terminal et shells

Regrouper les outils nécessaires à la personnalisation du terminal :

- installation des shells proposés ;
- choix du shell par défaut ;
- installation et configuration de Starship ;
- installation de polices Nerd Fonts.

Chaque changement doit être expliqué. Les fichiers de configuration existants doivent être sauvegardés avant leur modification.

### Personnalisation

Apporter une valeur ajoutée avec des ensembles de réglages cohérents.

Fonctions envisagées :

- enregistrer un profil de personnalisation ;
- appliquer ensemble un thème, des icônes, un curseur et des polices ;
- afficher un aperçu lorsque c’est possible ;
- restaurer les réglages précédents.

Le périmètre exact des réglages pris en charge devra être défini avant l’implémentation.

### Sauvegarde des réglages

Prévoir à terme l’export et la restauration des réglages que MintTweaks sait gérer.

Cette fonction doit annoncer clairement ce qui est sauvegardé. Elle ne constitue pas une sauvegarde complète du système ou des données personnelles.

## Fiabilisation avant l’ajout de modules

### Mode simulation

Garantir qu’un lancement en mode simulation empêche toutes les opérations destructives, y compris les suppressions effectuées directement par Python.

Points à vérifier :

- l’option `--dry-run` active réellement la simulation ;
- `MTK_DRY_RUN=1` couvre toutes les actions concernées ;
- le nettoyage des miniatures et de la corbeille ne supprime aucun fichier en simulation.

### Aperçu des suppressions

Garantir que la confirmation présente une information complète et fidèle à l’opération exécutée.

Points à vérifier :

- toutes les entrées de suppression des paquets orphelins passent par un aperçu ;
- la liste complète des paquets est consultable ;
- la confirmation ne promet pas une suppression limitée à une liste tronquée ;
- si l’état des paquets change, l’application gère cet écart avant la suppression.

### Validation sur Linux Mint

Tester les opérations réelles dans une machine virtuelle, notamment :

- refus de l’autorisation administrateur ;
- échec d’une commande APT ;
- sauvegarde et restauration Samba ;
- nettoyage et suppression de noyaux ;
- comportement de l’interface pendant les opérations.

Les tests automatisés doivent compléter ces essais.

### Distribution et présentation

- Automatiser les tests et vérifications avec GitHub Actions.
- Fournir un paquet `.deb` testé.
- Finaliser les instructions d’installation.
- Ajouter des captures d’écran représentatives.
- Indiquer clairement les versions et éditions de Linux Mint effectivement testées.

## Ordre de développement proposé

### Étape 1 — Consolider les modules existants

- [ ] Corriger et vérifier le mode simulation.
- [ ] Unifier les aperçus et confirmations de suppression.
- [ ] Tester les opérations dans une VM Linux Mint.
- [ ] Ajouter les vérifications automatiques avec GitHub Actions.
- [ ] Préparer un paquet `.deb` testé.

### Étape 2 — Créer l’accueil

- [ ] Ajouter le résumé du système.
- [ ] Ajouter les premiers diagnostics en lecture seule.
- [ ] Organiser les accès aux modules et aux outils utiles.

### Étape 3 — Ajouter le module Logiciels

- [ ] Définir un premier catalogue limité.
- [ ] Organiser les applications par usage.
- [ ] Afficher leur état d’installation.
- [ ] Gérer les installations APT et Flatpak retenues.
- [ ] Expliquer les sources d’installation proposées.

### Étape 4 — Ajouter Terminal et shells

- [ ] Définir les shells et outils pris en charge.
- [ ] Gérer le choix du shell par défaut.
- [ ] Ajouter Starship et les polices retenues.
- [ ] Sauvegarder les configurations avant modification.

### Étape 5 — Ajouter la personnalisation

- [ ] Définir les réglages pris en charge.
- [ ] Enregistrer et appliquer des profils.
- [ ] Prévoir les aperçus disponibles.
- [ ] Permettre la restauration des réglages précédents.

### Étape 6 — Évaluer l’export des réglages

- [ ] Définir le contenu d’un export.
- [ ] Vérifier sa compatibilité entre les systèmes pris en charge.
- [ ] Ajouter une restauration avec aperçu des changements.

## Fonctions à laisser pour plus tard

Les sujets suivants pourront être réévalués lorsque la base sera fiable :

- installation et changement d’environnement de bureau ;
- modifications du démarrage et du chargeur d’amorçage ;
- réglages avancés du noyau et de `sysctl` ;
- optimisations de performances dépendantes du matériel.

Ces fonctions nécessitent davantage de validation et de dépannage. Elles ne sont pas indispensables pour obtenir une première version utile.

## Architecture à conserver

Conserver Python et GTK 3 comme base actuelle, avec une séparation entre :

- le backend de chaque module, chargé de la logique et des commandes ;
- la page graphique du module ;
- les composants communs d’exécution, d’autorisation, de journalisation et de sauvegarde.

L’ajout d’un module doit réutiliser ces composants et s’accompagner de vérifications adaptées aux actions proposées.

## Critère de réussite

MintTweaks doit permettre à un utilisateur de Linux Mint de préparer, personnaliser et entretenir son système depuis une interface claire, avec des actions compréhensibles et un comportement prévisible.

La qualité du projet se mesurera à l’utilité et à la fiabilité des fonctions retenues.

