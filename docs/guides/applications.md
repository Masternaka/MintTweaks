# Applications

La section **Applications** accueille la liste personnelle des programmes à
installer depuis les dépôts officiels utilisés par Linux Mint. Le catalogue
reprend les **34 entrées** du fichier `app.md` fourni par l’utilisateur, sans
sélection automatique.

| Catégorie | Entrées demandées |
| --- | --- |
| Utilitaires | catfish, gparted, qbittorrent, transmission-gtk, lshw, fwupd, 7zip, unzip, stow, fontconfig, font-manager, flameshot |
| Utilitaires terminal | btop, fastfetch, git, curl, wget, ranger |
| Multimédia | strawberry, vlc, mpv |
| Virtualisation | qemu, virt-manager, distrobox, podman |
| Terminal | kitty |
| Développement | micro, meld |
| Polices | fonts-cascadia-code, fonts-firacode, fonts-hack, fonts-jetbrains-mono, fonts-noto, fonts-font-awesome |

Si `qemu` n’a pas de version candidate, le module recherche `qemu-system` dans les
sources officielles. Il utilise de même `p7zip-full` si `7zip` n’est pas disponible.
Le paquet réellement proposé est affiché. Les autres logiciels sans candidat
officiel restent indisponibles : la présence dans cette liste ne certifie pas
leur disponibilité sur toutes les versions de Mint.

## Utilisation

1. Ouvrir **Applications**, puis **Réanalyser** pour consulter les paquets.
2. Rechercher par nom, catégorie, description ou nom de paquet APT.
3. Cocher les applications disponibles qui ne sont pas déjà installées.
4. Cliquer sur **Prévisualiser les applications sélectionnées**.
5. Vérifier les versions, les sources et le plan complet APT, y compris les
   dépendances et mises à niveau. Confirmer pour demander l’autorisation
   administrateur et lancer l’installation.

Une recherche masque les lignes sans effacer les sélections. Un paquet déjà
installé reste visible avec sa version et n’est pas proposé à la réinstallation.
Cet état ne certifie pas la provenance historique du paquet installé.

Les applications absentes du cache APT ou dont la source ne peut pas être
vérifiée sont signalées comme indisponibles. Aucun dépôt, PPA ou clé n’est ajouté.
La section **Logiciels natifs** conserve son catalogue distinct de navigateurs
provenant de dépôts tiers.

## Transférer une sélection entre machines

La carte **Transférer une sélection d’applications** échange uniquement des choix
du catalogue Applications. Elle ne concerne pas les navigateurs de Logiciels
natifs, les outils du terminal ou leurs configurations.

### Exporter les choix

1. Cliquer sur **Choisir les applications à exporter…**. Le dialogue présente
   tout le catalogue, indépendamment du filtre de recherche de la page.
2. Choisir les entrées voulues. Les choix APT déjà cochés et la liste transférée
   en mémoire sont proposés dans ce dialogue. Les logiciels installés sont
   également sélectionnables, sans devenir candidats à la réinstallation.
3. Pour inclure explicitement les installations reconnues lors de la dernière
   analyse, utiliser **Ajouter les applications détectées à la dernière analyse**.
   Ce bouton modifie seulement les cases du dialogue d’export.
4. Valider au moins une entrée, lire l’aperçu JSON, puis choisir un nouveau fichier.

Le fichier contient des identifiants et les références de paquets du catalogue,
sans version, chemin, dépôt, réglage d’application ou donnée personnelle. Les
références restent celles des paquets principaux : `7zip` et `qemu`, même si la
machine utilise leurs alternatives. La machine de destination choisira ses
versions et alternatives selon ses propres métadonnées APT.

Les exports sont privés (`0600`), publiés complets et ne remplacent jamais un
fichier ou un lien déjà présent. Annuler le dialogue de choix, la confirmation
ou le sélecteur de fichier ne modifie pas les cases d’installation de la page.

### Importer sans installer

1. Choisir **Importer une sélection d’applications…**, puis le fichier JSON.
2. Lire l’aperçu avec la disponibilité observée sur cette machine. Les états
   distinguent les choix prêts pour APT, déjà installés, disponibles par le
   parcours GitHub des polices ou indisponibles/non vérifiés.
3. Confirmer. Le fichier est relu pour vérifier qu’il n’a pas changé et les états
   sont réanalysés avant de préparer les cases d’installation.

Les entrées APT disponibles sont ajoutées aux cases déjà cochées qui restent
valides. Les applications installées sont conservées, sans réinstallation. Les
choix indisponibles et les polices relevant du repli GitHub restent dans la liste
transférable, sans téléchargement ni installation. L’import fusionne ses choix
avec la liste de transfert déjà en mémoire.

Pour reprendre un choix devenu disponible, utiliser **Réanalyser**, puis
**Préparer la sélection transférée**. Cette action coche seulement les choix APT
disponibles. Consulter ensuite l’aperçu d’installation APT habituel ; chaque
police GitHub conserve son bouton et sa confirmation distincts. L’absence
confirmée du paquet officiel reste nécessaire pour le repli GitHub. Le fichier
d’import ne peut ni ajouter une source ni contourner ces contrôles.

**La liste de transfert est conservée pendant la session uniquement.** Le JSON
exporté permet de la réutiliser après réouverture. Les choix indisponibles ne
sont pas cochés automatiquement lorsqu’une nouvelle analyse les rend disponibles.
Le bouton de préparation reste une action explicite.

### Format et protection des fichiers

Le format comporte exactement `schema_version: 1`,
`kind: "minttweaks-application-selection"` et une liste non vide `applications`.
Chaque entrée contient uniquement `id` et `package`, qui doivent correspondre
au catalogue de la machine de destination. Une référence inconnue, substituée
ou dupliquée provoque un refus ; mettre le catalogue à jour si nécessaire.

Les champs supplémentaires, formats futurs, clés JSON dupliquées, fichiers de
plus de 32 Kio, liens symboliques et fichiers spéciaux sont refusés. Le fichier
source reste conservé. Une modification après aperçu demande une nouvelle
confirmation. Une erreur laisse la précédente liste de transfert en mémoire.

Les transferts ne demandent pas de droits administrateur et n’ajoutent aucun
dépôt. Les analyses utilisent les métadonnées APT existantes, sans actualisation
réseau. Les écritures d’export et la confirmation d’import utilisent la réservation
commune et apparaissent dans l’historique ; la sélection manuelle des cases reste
une action d’interface. Les transferts sont désactivés en simulation.

## Vérification des sources et de l’installation

L’inspection en lecture seule utilise `python3-apt` avec le Python système, en
mode isolé. Les origines de la version candidate doivent toutes être reconnues
comme officielles et approuvées par APT : Linux Mint et Ubuntu sur une base Ubuntu,
Linux Mint et Debian sur LMDE. Les miroirs sont reconnus par les métadonnées APT,
sans imposer un nom de domaine unique. Une version présente à la fois dans un
dépôt officiel et un dépôt tiers est refusée.

La même vérification couvre chaque paquet que la simulation APT propose
d’installer ou de mettre à niveau, y compris les dépendances. L’installation
utilise les versions demandées explicitement, refuse les suppressions et vérifie
à nouveau le plan et les sources après confirmation. Un changement impose un
nouvel aperçu. Le module ne rafraîchit pas les index : si nécessaire, le faire
dans le Gestionnaire de mises à jour de Mint avant de réanalyser.

Après installation, les versions des applications sélectionnées sont relues.
Un échec ou une vérification incomplète est affiché ; aucune désinstallation
automatique n’est tentée. Une seule modification peut être exécutée à la fois
dans MintTweaks. Le mode `--dry-run` n’installe rien.

## Polices absentes des dépôts : récupération GitHub

Un bouton **Récupérer cette police sur GitHub…** devient disponible uniquement
après confirmation qu’aucun candidat APT n’existe. Un cache APT illisible, une
erreur de diagnostic ou une source tierce ne déclenche pas ce repli. La présence
d’un paquet officiel reste prioritaire.

| Famille | Dépôt amont |
| --- | --- |
| Cascadia Code | [microsoft/cascadia-code](https://github.com/microsoft/cascadia-code) |
| Fira Code | [tonsky/FiraCode](https://github.com/tonsky/FiraCode) |
| Hack | [source-foundry/Hack](https://github.com/source-foundry/Hack) |
| JetBrains Mono | [JetBrains/JetBrainsMono](https://github.com/JetBrains/JetBrainsMono) |
| Font Awesome | [FortAwesome/Font-Awesome](https://github.com/FortAwesome/Font-Awesome) |
| Noto | [notofonts/noto-fonts](https://github.com/notofonts/noto-fonts), [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk), [googlefonts/noto-emoji](https://github.com/googlefonts/noto-emoji) |

L’aperçu indique les versions ou révisions, les URL, le volume à télécharger et
le dossier cible. Le paquet GitHub peut différer en version et en composition du
paquet de la distribution. Noto rassemble les TTF de `hinted/ttf/` du dépôt
historique désormais archivé, les collections CJK Sans/Serif Regular et Bold et
Noto Color Emoji. Ce repli ne prétend pas reproduire exactement le métapaquet APT
de chaque version de Mint ; il peut représenter un téléchargement important.

Après confirmation, seuls les fichiers TTF, OTF, TTC et leurs licences sont
installés dans `$XDG_DATA_HOME/fonts/minttweaks/<paquet>/`, soit par défaut
`~/.local/share/fonts/minttweaks/<paquet>/`. Aucun script amont n’est exécuté,
aucune police existante n’est remplacée, aucun droit administrateur n’est requis.
Fontconfig est actualisé avec `fc-cache`. Fermer puis rouvrir les applications
peut être nécessaire pour voir les polices.

Les archives des versions stables sont identifiées via l’API GitHub. Leur
SHA-256 amont est vérifié lorsqu’il est fourni ; il n’est pas disponible pour
toutes les anciennes versions. Les fichiers Noto sont liés à une révision Git
précise et vérifiés contre leur identifiant de blob. Toutes les copies installées
sont ensuite suivies par un manifeste SHA-256 local. Les chemins dangereux,
les liens symboliques, les signatures de fichiers invalides et les tailles
excessives sont refusés. Le mode simulation n’effectue aucun téléchargement
de police ni installation.

## Maintenir la liste au projet

La liste est centralisée dans
[`catalog.py`](../../minttweaks/modules/applications/catalog.py). Chaque entrée
`Application` comporte un identifiant stable, un nom, un nom de paquet APT exact,
une catégorie et une description facultative. Les textes traduisibles doivent
être passés à `_()` pour être extraits par `make pot`.

Les noms de logiciels fournis ultérieurement devront être associés aux bons
paquets et leur disponibilité vérifiée selon la version de Mint. Une application
uniquement disponible via Flatpak ou un dépôt tiers ne sera pas ajoutée comme
paquet officiel disponible. Le catalogue n’accepte ni URL ni commande shell.

## Limites de validation

Les tests automatisés utilisent des caches et commandes APT simulés : ils
vérifient le filtrage des origines, les dépendances, les confirmations et les
plans périmés. Le rendu GTK, la lecture du cache réel avec `python3-apt`, les
miroirs officiels et l’installation avec polkit restent à vérifier sous Mint.

## Détails d’installation

Chaque entrée présente un volet avec sa méthode, sa portée, sa source attendue,
les versions ou révisions disponibles et les indications de mise à jour et de
retrait. Voir [Comprendre les installations](installations.md) pour la distinction
entre candidat vérifié, paquet déjà installé et copie utilisateur.
