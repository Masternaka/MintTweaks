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
