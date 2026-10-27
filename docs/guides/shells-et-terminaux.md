# Shells et terminaux

La page privilégie l’ajout d’utilitaires pour le terminal et le shell, avec un
catalogue de **32 outils** répartis par usage. Le shell de connexion, l’invite et
l’apparence de Kitty/Alacritty restent accessibles dans leurs onglets.
L’assistant après installation peut ouvrir cette page comme étape facultative.

## Catalogue d’utilitaires

La sélection rassemble des projets courants et bien établis. Elle ne prétend pas
constituer un classement statistique de leur utilisation. Chaque entrée affiche
son objectif, son paquet APT, un exemple de commande lorsqu’il est pertinent et
un lien vers la documentation du projet. Les exemples sont consultables et ne
sont jamais exécutés par MintTweaks.

| Usage | Outils proposés |
| --- | --- |
| Navigation et recherche | fzf, zoxide, ripgrep, fd |
| Fichiers et espace disque | bat, eza, tree, ncdu, duf |
| Développement et données | Git, lazygit, delta, Neovim, jq, curl, Wget |
| Sessions et surveillance | tmux, btop, htop, Fastfetch |
| Améliorations du shell | tldr, direnv, Atuin, bash-completion, zsh-autosuggestions, zsh-syntax-highlighting, Starship |
| Shells et terminaux | Bash, Zsh, Fish, Kitty, Alacritty |

**Sélectionner les outils de départ** coche seulement les outils disponibles et
absents parmi **fzf, zoxide, ripgrep, fd, bat, eza, tmux, btop et tldr**. Ce bouton
ne lance aucune installation. **Vider la sélection** permet de repartir sans
choix. Il est aussi possible de choisir chaque outil individuellement.

Les noms de paquets et de commandes sont distingués : fd utilise le paquet
`fd-find` et généralement la commande `fdfind`, bat peut fournir `batcat`, ripgrep
fournit `rg`, Neovim fournit `nvim` et delta utilise le paquet `git-delta`.
Ces variantes sont prises en compte pour détecter les exécutables existants.
Les extensions sans exécutable sont détectées par leur paquet.

## Installer les outils

La page affiche les paquets ou exécutables détectés et les versions candidates
APT. Cocher les outils disponibles puis choisir **Prévisualiser l’installation
des outils**. La confirmation montre le plan complet, dépendances et mises à jour
comprises. MintTweaks vérifie à nouveau les versions et opérations avant de
solliciter polkit ; une suppression proposée bloque l’installation. Les versions
installées sont relues après l’opération.

Cette page utilise les dépôts APT déjà configurés sur la machine, y compris ceux
de Mint : la restriction aux applications tierces concerne le module Logiciels
natifs, pas cette section. La disponibilité dépend de la version de Mint et des
sources configurées ; Starship, Atuin, Fastfetch ou lazygit peuvent notamment ne
pas avoir de candidat. Chaque outil reste visible avec son indisponibilité et son
lien officiel. MintTweaks n’exécute pas de script téléchargé et n’ajoute pas de
dépôt automatiquement.

L’option **Configurer les intégrations proposées après installation** est cochée
par défaut. Choisir le **shell concerné** (Bash, Zsh ou Fish). Après installation
et vérification des paquets, un second aperçu montre les différences des fichiers
de démarrage et les effets de chaque intégration. Confirmer pour écrire la
configuration avec sauvegarde. Annuler ce second aperçu conserve les paquets et
laisse les fichiers de démarrage intacts. Une erreur de préparation indique que
les paquets sont installés mais que la configuration n’a pas été appliquée.

## Intégrations et configuration

L’onglet **Intégrations du shell** permet aussi d’activer ou retirer les
intégrations d’outils déjà installés. Choisir le shell, cocher les outils puis
prévisualiser l’activation ou le retrait. Chaque outil possède son bloc identifié ;
le retrait d’un bloc conserve les autres intégrations et les réglages extérieurs.

| Outil | Configuration proposée |
| --- | --- |
| fzf | Raccourcis et complétions fournis par la version installée ; scripts du paquet pour les versions antérieures à 0.48, initialisation intégrée pour les plus récentes |
| zoxide | Initialisation du suivi des dossiers et des commandes `z` / `zi` |
| bat / fd | Alias `bat` vers `batcat` et `fd` vers `fdfind` seulement si les noms ne sont pas déjà disponibles |
| Starship | Bloc d’initialisation et fichier d’invite privé déjà décrits ci-dessous |
| delta | `GIT_PAGER=delta` dans ce shell si cette variable n’est pas définie ; aucun fichier Git global ou local modifié |
| Atuin | Initialisation de l’historique local ; Ctrl+R prend la place de celui de fzf lorsque les deux sont activés |
| direnv | Initialisation du hook ; chaque projet doit ensuite être autorisé par l’utilisateur |
| bash-completion | Chargement des complétions dans Bash si elles ne sont pas déjà initialisées |
| zsh-autosuggestions | Chargement du module dans Zsh |
| zsh-syntax-highlighting | Chargement du module à la fin des blocs gérés, après les autres widgets Zsh |

Les extensions réservées à Bash ou Zsh sont signalées comme non applicables dans
les autres shells. Zsh reçoit une initialisation protégée de son système de
complétion si aucune initialisation `compinit` n’est repérée. Les outils autonomes
(ripgrep, jq, btop, Git, Neovim, tmux, etc.) utilisent leurs réglages par défaut ;
MintTweaks ne leur ajoute pas de distribution de plugins ou de configuration
personnelle arbitraire. Les profils visuels Kitty/Alacritty restent dans leur
onglet avec leurs propres choix de police et de couleurs.

Une initialisation manuelle directe déjà présente, un module déclaré dans un
tableau `plugins=(...)` reconnu, un raccourci `z` personnalisé repéré ou un bloc
mal formé provoquent un refus de configuration. Les autres fichiers chargés par
le shell et les frameworks complexes ne sont pas analysés intégralement. Lire
les différences si une configuration personnelle est déjà en place.

Les scripts d’intégration nécessaires et les exécutables sont contrôlés avant
application. Un changement de fichier ou de plan depuis l’aperçu demande un nouvel
aperçu. L’application vérifie les octets écrits ; elle ne lance pas le shell pour
exécuter ces initialisations. **Ouvrir un nouveau terminal interactif du shell
choisi** pour les charger et vérifier leur comportement.

Atuin commence alors à enregistrer les nouvelles commandes localement ; aucun
compte, import de l’ancien historique ou synchronisation n’est configuré.
MintTweaks ne lance pas `direnv allow`. Le retrait d’un bloc ne recharge pas les
terminaux déjà ouverts et ne supprime pas les données créées ensuite par l’outil.
Les sauvegardes communes permettent aussi de rétablir les fichiers précédents.

## État des intégrations, recherche et filtres

Le catalogue et l’onglet des intégrations indiquent l’état pour le shell choisi :
absent, installé avec ses réglages par défaut, intégration à configurer,
configuration gérée présente, intégration manuelle reconnue, non applicable ou
configuration à revoir. Un fichier inaccessible, un bloc mal formé, un exécutable
absent ou un fichier géré modifié ne produit pas un état « actif ».

**Configuré** signifie que les fichiers attendus ont été retrouvés, pas qu’un
terminal déjà ouvert les a chargés. L’interface invite à vérifier dans un nouveau
terminal. Le diagnostic reste une lecture de fichiers et de versions ; il
n’exécute pas les fichiers de démarrage et ne prétend pas analyser tous les
frameworks ou fichiers inclus par l’utilisateur.

Rechercher par nom, paquet ou description. Les filtres proposent tous les outils,
les outils installés, ceux disponibles à l’installation et les intégrations
compatibles avec le shell concerné. Les sélections masquées sont conservées et
restent incluses dans l’aperçu d’installation.

## Réglages personnels des outils

L’onglet **Réglages des outils** propose des options individuelles, sans ensemble
prédéfini d’outils ou de réglages à appliquer :

| Outil | Options disponibles |
| --- | --- |
| Starship | Affichage Git, ligne vide, caractère de l’invite et couleur |
| fzf | Hauteur, disposition, couleurs et aperçu des 100 premières lignes avec head |
| bat | Thème TwoDark/GitHub et informations affichées |
| eza | Liste détaillée, informations Git et arborescence via `mtk-eza` |
| tmux | Préfixe Ctrl+B/Ctrl+A, souris et position de la barre d’état via `mtk-tmux` |

Chaque bouton prépare les différences pour l’outil choisi. Les réglages déjà
enregistrés pour les autres outils sont conservés. Les outils et le shell doivent
être installés. Les hooks fzf/bat/Starship nécessaires sont aussi proposés dans
cet aperçu. Les variables et fonctions sont chargées par un bloc interactif vers
un fichier MintTweaks séparé. Les réglages Starship et tmux correspondent à des
fichiers gérés communs aux shells ; modifier ces options actualise leurs valeurs
communes dans les préférences.

`mtk-eza` et `mtk-tmux` permettent d’utiliser les options sans modifier les
configurations habituelles. Tmux utilise le serveur nommé `minttweaks` ; une
session existante conserve les options déjà chargées par son serveur. Les
paramètres fzf et bat s’appliquent au nouvel environnement du shell, où d’autres
réglages personnels peuvent encore les remplacer. L’aperçu fzf lit des fichiers
lors de son utilisation dans le terminal, jamais pendant la préparation dans
MintTweaks.

## Alias personnels

Dans **Alias personnels**, choisir un shell, saisir un nom et une commande, puis
prévisualiser l’enregistrement. Pour modifier un alias, le sélectionner et choisir
**Charger l’alias sélectionné** avant de changer sa commande. Le bouton de retrait
supprime uniquement l’alias géré portant le nom saisi.

Les noms sont limités à 32 caractères et les commandes à une ligne de 1 024
caractères ; 64 alias au maximum sont autorisés par shell, sous réserve de la
limite de taille du fichier de préférences. Les noms réservés et les conflits
repérés avec une définition manuelle sont refusés. Le masquage d’un exécutable
existant est annoncé dans la confirmation. Les définitions présentes dans des
fichiers externes ne sont pas entièrement inspectées.

Les commandes restent des chaînes protégées lors du chargement. Pour Fish, une
fonction diffère leur évaluation jusqu’à l’appel du raccourci. MintTweaks ne les
exécute pas. Un raccourci est une commande personnelle : lire sa valeur complète
avant d’accepter un import provenant d’une autre personne.

## Export et import de la configuration personnelle

L’onglet **Export et import** transporte les choix de l’utilisateur dans un JSON
versionné. Il ne fournit aucun profil prédéfini de type « Essentiel »,
« Développement » ou « Administration ».

L’export contient les outils du catalogue détectés comme installés, les choix
actuellement cochés, les intégrations gérées reconnues, les réglages des outils,
les alias et les choix enregistrés d’apparence Kitty/Alacritty. Les fichiers de
démarrage bruts, configurations manuelles externes, historiques, données Atuin,
identité Git et shell de connexion ne sont pas exportés. Les commandes d’alias
peuvent toutefois contenir des chemins ou valeurs sensibles ; le JSON complet est
présenté avant écriture. Le fichier privé est créé en `0600` et un fichier
existant n’est jamais remplacé automatiquement.

L’import vérifie le format, les identifiants, les types et plages des réglages,
la compatibilité des extensions avec les shells, les polices et la disponibilité
des paquets dans les sources APT locales. Une police absente doit être installée
séparément. Si des outils manquent, une confirmation présente leur plan APT ;
après installation vérifiée, une autre confirmation présente les fichiers de
configuration. Annuler ce second aperçu conserve les paquets installés.

Les chemins, formats Alacritty et scripts d’intégration sont recalculés pour la
machine cible. Les commandes d’alias restent littérales : leurs chemins personnels
ne sont pas réécrits. L’import fusionne les options et alias gérés, sans retirer
les outils locaux ou les autres réglages gérés ; un alias importé portant le même
nom remplace sa valeur gérée après aperçu. Il ne change ni le shell de connexion
ni les dépôts APT et ne télécharge aucune police. Un fichier invalide est refusé
sans remise à zéro des préférences locales.

## Choisir le shell de connexion

Choisir un Bash, Zsh ou Fish exécutable présent dans `/etc/shells`, puis consulter
l’aperçu. Le compte concerné est toujours celui de l’utilisateur Linux connecté,
hors root. L’ancienne valeur est enregistrée avant l’appel à `chsh` via polkit,
puis la base des comptes est relue pour vérifier le résultat.

Le changement prend effet lors d’une **nouvelle session de connexion**. Il ne
remplace pas le processus des terminaux déjà ouverts. **Restaurer le shell de
connexion précédent** présente un nouvel aperçu et requiert la même autorisation.
Si le compte a changé entre-temps, l’opération est refusée.

## Personnaliser l’invite

Starship doit déjà être accessible dans le PATH. Choisir Bash, Zsh ou Fish et
prévisualiser l’activation. MintTweaks ajoute un bloc identifié dans `.bashrc`,
`.zshrc` ou `fish/config.fish`. Les alias et réglages extérieurs au bloc sont
conservés. Une initialisation Starship manuelle ou un bloc mal formé provoquent
un refus. Un `ZDOTDIR` personnalisé doit être géré manuellement.

L’invite proposée montre le dossier, la branche Git, son état et un caractère
ASCII ; elle ne nécessite pas de Nerd Font. **Prévisualiser le retrait de l’invite
gérée** supprime seulement le bloc MintTweaks. Fermer et rouvrir le terminal pour
charger la configuration. L’application n’exécute pas les fichiers de démarrage.

## Personnaliser Kitty et Alacritty

Installer le terminal, puis choisir un profil clair ou sombre, une police déjà
installée et une taille de 8 à 32 points. Le profil est enregistré séparément et
une entrée **Kitty — MintTweaks** ou **Alacritty — MintTweaks** est ajoutée au menu
Mint. Ouvrir cette entrée pour utiliser les réglages proposés.

Les configurations habituelles de Kitty et Alacritty sont conservées. L’action
ne change pas le terminal par défaut du système. Alacritty reçoit un fichier YAML
pour les versions antérieures à 0.13, TOML à partir de 0.13 ; une version non
identifiable provoque un refus. La liste des polices provient de Fontconfig,
avec `monospace` comme repli. Aucun téléchargement de police n’est effectué.

## Fichiers et retour en arrière

| Usage | Chemin par défaut |
| --- | --- |
| Démarrage Bash / Zsh | `~/.bashrc`, `~/.zshrc` |
| Démarrage Fish | `~/.config/fish/config.fish` |
| Préférences déclaratives | `~/.config/minttweaks/terminal/preferences.json` |
| Variables et alias gérés | `~/.config/minttweaks/terminal/settings.{bash,zsh,fish}` |
| Options tmux séparées | `~/.config/minttweaks/terminal/tmux.conf` |
| Profils gérés | `~/.config/minttweaks/terminal/` |
| Entrées du menu | `~/.local/share/applications/minttweaks-{kitty,alacritty}.desktop` |
| Sauvegardes de fichiers | `~/.local/share/minttweaks/terminal-backups/files/` |
| Valeurs précédentes du shell | `~/.local/share/minttweaks/terminal-backups/accounts/` |

`XDG_CONFIG_HOME` et `XDG_DATA_HOME` sont respectés lorsqu’ils sont définis.
Les sauvegardes privées en JSON contiennent les octets précédents (encodés en
base64), les permissions et l’absence éventuelle du fichier. Elles peuvent donc
contenir des informations personnelles présentes dans les fichiers de démarrage.
Elles ne sont pas supprimées automatiquement.

Chaque écriture présente les différences complètes et sauvegarde tous les
fichiers concernés avant la première modification. Un fichier différent de
l’aperçu, symbolique, non régulier ou trop volumineux provoque un refus. Les
écritures utilisent un remplacement atomique fichier par fichier, puis une
relecture. En cas d’échec partiel, MintTweaks tente de rétablir les fichiers déjà
modifiés ; une modification extérieure différente est conservée et signalée.
Cela ne constitue pas une transaction atomique entre plusieurs fichiers ni un
verrou contre un programme extérieur.

L’onglet **Sauvegardes des configurations** permet de prévisualiser puis confirmer
une restauration, elle-même précédée d’une sauvegarde. Un fichier créé par
MintTweaks peut ainsi être retiré. Les cibles d’une sauvegarde doivent correspondre
aux chemins du compte courant. Une restauration ancienne peut remplacer des
modifications ultérieures : lire les différences avant de confirmer.

Les modifications utilisent la réservation commune de MintTweaks. Elles sont
désactivées en simulation et les fonctions backend de simulation ne créent ni
fichier ni sauvegarde.

## Validation et références

Les tests hors ligne couvrent les plans APT et leur changement, les vérifications
après commande, les blocs d’invite, les deux formats Alacritty, les fichiers
séparés, les sauvegardes et restaurations, les échecs partiels, la simulation et
les confirmations GTK avec doublures et les intégrations des trois shells.
La syntaxe Bash/Zsh générée est contrôlée lorsque le binaire est disponible sur
l’hôte, sans exécuter les blocs. Les tests n’exécutent ni installation ni `chsh`
réel. Les essais d’affichage GTK, de lancement des deux terminaux et de nouvelle
session sous Mint restent à consigner dans la [recette Mint](../validation/linux-mint.md).

Références officielles : [initialisation Starship](https://starship.rs/guide/),
[options Kitty](https://sw.kovidgoyal.net/kitty/invocation/),
[configuration Alacritty](https://alacritty.org/config-alacritty.html),
[historique Alacritty](https://alacritty.org/changelog_0_13_0.html),
[format des entrées de menu](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html) et
[manuel chsh Ubuntu](https://manpages.ubuntu.com/manpages/noble/man1/chsh.1.html).

Pour le catalogue : [fzf](https://github.com/junegunn/fzf),
[zoxide](https://github.com/ajeetdsouza/zoxide),
[bat](https://github.com/sharkdp/bat), [fd](https://github.com/sharkdp/fd),
[suggestions Zsh](https://github.com/zsh-users/zsh-autosuggestions) et
[coloration Zsh](https://github.com/zsh-users/zsh-syntax-highlighting).
Chaque autre projet dispose de son lien officiel dans la page.

Initialisations vérifiées dans les guides officiels :
[direnv](https://direnv.net/docs/hook.html),
[Atuin](https://docs.atuin.sh/18.17/guide/installation/),
[fzf](https://github.com/junegunn/fzf#setting-up-shell-integration) et
[delta](https://dandavison.github.io/delta/configuration.html).

Références des réglages : [Starship](https://starship.rs/config/),
[fzf](https://github.com/junegunn/fzf#environment-variables),
[bat](https://github.com/sharkdp/bat#configuration-file),
[eza](https://github.com/eza-community/eza/blob/main/man/eza.1.md),
[tmux](https://man.openbsd.org/tmux) et
[implémentation des alias Fish](https://github.com/fish-shell/fish-shell/blob/master/share/functions/alias.fish).
