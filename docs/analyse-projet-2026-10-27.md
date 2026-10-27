# Analyse et avis sur MintTweaks

Date : 27 octobre 2026. Sources examinées : branche `main`, commit
`80ffcfc7393ecd75149ad5bf401a776986752a0c`, version applicative `0.1.3`.

## Mon avis

**MintTweaks a une bonne base technique et une utilité claire pour Linux Mint
Cinnamon. Je poursuivrais le projet, en consacrant maintenant une étape à la
fiabilité et aux essais réels avant d'ajouter des fonctions.**

Le projet rassemble des opérations dispersées dans une interface native, avec
des aperçus, des confirmations et des sauvegardes. Sa valeur est surtout de
rendre ces opérations plus compréhensibles et récupérables. La séparation de la
logique système et de GTK, ainsi que les tests exécutables hors de Linux, sont
de bons choix pour sa maintenance.

En revanche, je le considérerais actuellement comme un **candidat de développement
à éprouver en VM**, plutôt que comme un outil dont la fiabilité quotidienne est
déjà démontrée. Le compte rendu de validation du dépôt reste un modèle non rempli,
et un défaut dans la chaîne de validation Samba mérite une correction prioritaire.

## Périmètre et méthode

L'examen porte sur le code Python, les neuf modules, les auxiliaires privilégiés,
les tests, les traductions, l'installation, le workflow GitHub et la documentation.
Il associe lecture du code, exécution des contrôles du dépôt et une reproduction
ciblée en répertoire temporaire. Ce n'est pas un audit exhaustif de sécurité.

L'environnement de vérification est macOS avec Python `3.9.6`. Aucun changement
de configuration système, aucune installation APT et aucun lancement réel de
l'interface GTK n'ont été réalisés.

| Vérification exécutée | Résultat |
| --- | --- |
| `make test` | 460 tests recensés : 459 réussis, 1 ignoré, aucun échec |
| Test ignoré | Comparaison des versions Debian, car `dpkg` est absent |
| `make check` | Réussi : compilation Python, syntaxe du script de publication, extraction et compilation gettext |
| Traductions | Modèle de 670 chaînes ; catalogue français de 671 entrées signalées traduites par l'outil |
| Reproduction ciblée Samba | Acceptation d'un lien symbolique et copie d'un contenu modifié après validation reproduites hors système |

Ces résultats ne prouvent ni l'installation du `.deb`, ni le comportement de
polkit, ni la compatibilité des commandes avec chaque version de Mint. La CI
distante et ses pièces jointes n'ont pas été validées dans cette analyse.

## Ce que je trouve réussi

### Une architecture adaptée au problème

La couche [`core/runner.py`](../minttweaks/core/runner.py) centralise les commandes
et permet d'injecter des doubles de test. Les modules séparent généralement
`backend.py` et `page.py`. Le terminal est déjà réparti entre catalogue,
intégrations, configuration et transfert : cette organisation aide à contenir
la complexité de ce module.

Le choix Python/GTK 3 est cohérent avec une application ciblant Cinnamon. Je ne
vois pas de justification, dans le code examiné, à une réécriture complète ou à
un changement de technologie avant la validation du fonctionnement actuel.

### Des protections concrètes

- Les commandes passent sous forme de listes d'arguments, sans interprétation
  par un shell ; les mots de passe Samba sont transmis par l'entrée standard.
- Une réservation commune dans [`ui/widgets.py`](../minttweaks/ui/widgets.py)
  refuse les modifications concurrentes au sein de l'application et reste
  active jusqu'au traitement du résultat par GTK.
- Le moteur de fichiers utilisateur dans
  [`core/userfiles.py`](../minttweaks/core/userfiles.py) compare l'état courant à
  l'aperçu, sauvegarde, écrit par remplacement et tente une récupération en cas
  d'échec. Les erreurs de récupération sont remontées.
- L'installation des navigateurs vérifie la provenance attendue, fixe les
  versions, compare un nouvel aperçu puis contrôle le résultat installé.
- Les profils Cinnamon se limitent à sept réglages autorisés. L'export terminal
  transporte des choix structurés plutôt que des scripts de démarrage arbitraires.

Ces mécanismes montrent un souci de maîtrise des effets. Ils réduisent les
risques ; ils ne constituent pas une transaction globale avec APT, systemd ou
les autres applications ouvertes sur la machine.

### Une documentation honnête et utile

Les guides, la feuille de route et la recette distinguent ce qui existe dans le
code de ce qui a réellement été testé. Les exclusions de périmètre sont saines :
Timeshift et les gestionnaires Mint existants restent dans leurs applications.
Cette discipline mérite d'être conservée.

## Points à traiter, par priorité

### 1. Priorité haute — Figer le candidat Samba avant sa validation

**Constat reproduit.** Dans [`data/mtk-root`](../data/mtk-root), `check_source()`
utilise `Path.stat()` et suit donc les liens symboliques. Puis
`install_smbconf()` appelle `testparm` sur le chemin fourni, avant de relire ce
même chemin avec `shutil.copyfile()` pour préparer l'installation.

Le contenu validé n'est donc pas garanti identique au contenu installé. Le
fichier peut changer entre ces étapes, notamment parce qu'il appartient encore
à l'utilisateur appelant.

La reproduction a chargé les fonctions avec `runpy`, redirigé la destination
et les sauvegardes vers un répertoire temporaire, simulé `os.chown` et remplacé
`run_testparm` par une fonction simulant une validation réussie puis une
modification du candidat. L'installation a renvoyé `0` et copié la version
modifiée. Un lien vers un fichier ordinaire a aussi été accepté par
`check_source()`. Aucun `testparm` réel ni appel root n'a été exécuté.

**Impact :** la garantie de validation avant installation peut être contournée
pendant une opération autorisée. Cela ne démontre pas, à lui seul, une élévation
de privilèges sans autorisation polkit.

**Correction conseillée :** ouvrir le candidat sans suivre les liens, vérifier
son descripteur avec `fstat`, lire une quantité bornée, puis créer une copie
privée dans un emplacement contrôlé par root. Valider cette copie et installer
exactement les octets validés. Ajouter des tests de remplacement du candidat,
de lien symbolique et de dépassement de taille pendant la lecture.

### 2. Priorité haute — Exécuter et consigner la recette Mint

**État documentaire constaté :**
[`validation/compte-rendu.md`](validation/compte-rendu.md) indique que les essais
ne sont pas effectués. Les tests utilisant de faux objets GTK sont utiles pour
les interactions logiques, mais ne valident pas le rendu ni une session Cinnamon.

Je commencerais par une VM avec instantané sur une version de Mint choisie
explicitement. Il faut y construire et installer le paquet exact, tester les
neuf pages, les refus polkit, les erreurs APT et les restaurations, puis ouvrir
de nouvelles sessions Bash, Zsh et Fish pour les intégrations concernées.

Le livrable attendu est un compte rendu avec version de Mint, commit, somme du
paquet, résultats et anomalies. Les familles Mint 20, 21 et 22 annoncées comme
cibles dans le README doivent être vérifiées séparément avant d'être présentées
comme effectivement compatibles.

### 3. Priorité moyenne — Présenter le plan APT de purge des noyaux

**Constat par lecture :** `purge_kernels()` dans
[`maintenance/backend.py`](../minttweaks/modules/maintenance/backend.py) refuse
les objets marqués comme noyau courant, puis lance directement
`apt-get purge -y`. L'interface confirme les versions sélectionnées, mais ne
présente pas le plan complet de résolution APT comme le module Logiciels natifs.

**Risque à vérifier sous Mint :** les suppressions réelles peuvent inclure des
paquets supplémentaires, et l'état des paquets peut évoluer depuis l'analyse.
La réservation interne ne bloque pas les autres gestionnaires de paquets.

Je conseille une simulation de la purge, l'affichage des suppressions complètes
et une nouvelle vérification des protections et du plan avant exécution. Ce
point est une différence de garde-fous constatée, pas une perte de noyau
reproduite lors de cette analyse.

### 4. Priorité moyenne — Borner les sorties gardées en mémoire

**Constat par lecture :** `SubprocessRunner.stream()` accumule les lignes dans
une liste et conserve également la ligne partielle. La fenêtre ajoute la sortie
à un `Gtk.TextBuffer`. Les journaux sur disque ont une rotation, mais ces deux
mémoires de sortie n'ont pas de limite explicite.

Une commande très bavarde peut donc consommer beaucoup de mémoire et charger
la boucle GTK de nombreux rappels. Le délai de commande ne borne pas son volume
de sortie ; une commande administrative reste surveillée après ce délai.

Je conseille un tampon limité pour l'affichage, des mises à jour GTK regroupées
et un signalement des sorties tronquées. Le flux doit continuer à être drainé
pour ne pas bloquer le processus enfant. Aucun essai de saturation mémoire n'a
été effectué ici.

### 5. Priorité moyenne — Adapter les publications aux changements documentaires

**Comportement configuré :**
[`release.yml`](../.github/workflows/release.yml) se déclenche à chaque push sur
`main`, sans filtre de chemins. `tools/release_plan.py` prévoit alors une
préversion de développement, et le workflow construit puis publie les pièces
jointes si les étapes réussissent. Une modification documentaire est donc
éligible à cette publication automatique.

Je séparerais les contrôles de documentation de la décision de construire une
préversion, ou j'ajouterais une condition sur les fichiers modifiés. L'objectif
est de conserver une validation utile tout en évitant des préversions sans
changement fonctionnel. Cette analyse ne modifie pas le workflow.

### 6. Priorité basse — Réduire quelques sources de dette

- La page Samba approche 900 lignes. Extraire progressivement les dialogues et
  les sections indépendantes faciliterait sa lecture ; ce n'est pas une raison
  de refondre toute l'interface.
- Le champ `Homepage` de [`debian/control`](../debian/control) pointe vers
  `github.com/gabrielchapdelaine/MintTweaks`, alors que le remote et le README
  utilisent `github.com/Masternaka/MintTweaks`. Harmoniser la métadonnée avec la
  destination actuelle ; la disponibilité de l'ancienne URL n'a pas été vérifiée.
- Le sous-titre et le texte « À propos » de la fenêtre citent encore surtout
  entretien, services, Samba et Firefox. Les actualiser aiderait à comprendre
  le périmètre des neuf modules.

## La suite que je privilégierais

| Étape | Résultat attendu |
| --- | --- |
| 1. Durcir l'auxiliaire Samba | Même contenu validé et installé, contrôles de fichiers testés |
| 2. Valider un candidat sous Mint | Paquet installé, interface réelle essayée, restaurations démontrées et compte rendu rempli |
| 3. Renforcer purge et sortie des commandes | Plan complet confirmé et affichage borné |
| 4. Clarifier la distribution | Compatibilités prouvées, métadonnées cohérentes et préversions pertinentes |
| 5. Reprendre les ajouts ciblés | Priorités choisies à partir des retours d'utilisation réelle |

Mon choix serait de consolider l'entretien, les profils et les réglages personnels
du terminal, qui donnent déjà au projet une identité utile. Le catalogue est
suffisamment large pour cette étape. La meilleure progression maintenant serait
de pouvoir montrer, pour un paquet précis : installation réussie, opération
compréhensible, échec correctement signalé et restauration vérifiée.
