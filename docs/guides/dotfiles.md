# Gestion des dotfiles

La section **Dotfiles** clone un dépôt GitHub et permet d’activer une
configuration à la fois avec GNU Stow, dans le compte utilisateur courant.

1. Cliquez sur **Installer Git et Stow** si nécessaire. Le plan APT complet est
   présenté avant l’autorisation administrateur, puis vérifié à nouveau.
2. Saisissez une URL `https://github.com/utilisateur/dotfiles.git` ou
   `git@github.com:utilisateur/dotfiles.git`. Aucun jeton ne doit figurer dans l’URL.
   Pour un dépôt privé, préparez votre authentification Git au préalable.
3. Choisissez le dossier parent du clone. Le champ **Dossier local des dotfiles**
   indique le nouveau dossier à créer ; il ne doit pas déjà exister. Vous pouvez
   aussi ouvrir directement un dossier de dotfiles existant.
4. Choisissez le dossier cible des liens : votre dossier personnel par défaut.
5. Cliquez sur **Analyser les configurations**, puis sur **Stow** à côté de la
   configuration souhaitée. Vérifiez la commande, la simulation et la liste des
   fichiers à sauvegarder avant de confirmer.
6. Pour revenir à la configuration précédente, cliquez sur **Annuler le Stow**
   sur la même ligne, puis confirmez les liens à retirer et les fichiers à restaurer.

## Transférer les références entre machines

La carte **Transférer les références Dotfiles** échange un fichier JSON contenant
uniquement l’URL GitHub, les noms des configurations souhaitées et l’option
`--dotfiles`. Les chemins de la machine source, les fichiers de configuration,
les sauvegardes, les identifiants Git et les clés SSH ne sont pas copiés. Le
fichier ne fixe ni branche ni révision du dépôt.

### Exporter

1. Renseigner l’URL GitHub HTTPS ou SSH sans jeton, puis analyser le dossier local.
   Pour un dossier existant ouvert sans URL, saisir celle-ci puis réanalyser.
2. Choisir **Exporter une référence Dotfiles…**, puis cocher les configurations
   à inclure. Ces cases sont indépendantes des boutons **Stow** et **Annuler le Stow**.
3. Le bouton **Ajouter les configurations gérées ou les liens détectés** permet
   d’inclure explicitement les configurations reconnues dans la dernière analyse.
   Sans cette action, les nouvelles configurations ne sont pas cochées automatiquement.
4. Lire l’aperçu JSON et choisir un nouveau fichier. Son contenu correspond à
   l’aperçu ; les permissions sont privées (`0600`) et aucun fichier existant
   n’est remplacé.

Une référence déjà importée propose ses noms dans le dialogue d’export, même si
certains n’ont pas encore été retrouvés localement. Ils restent des choix à
examiner et ne constituent pas une preuve de disponibilité dans le dépôt distant.

### Importer et adapter les dossiers locaux

1. Choisir **Importer une référence Dotfiles…**, puis sélectionner le JSON.
2. Choisir sur cette machine le dossier local du dépôt ou une nouvelle destination
   de clone dont le parent existe. Choisir aussi un dossier cible existant pour
   les liens, situé en dehors du dossier du dépôt.
3. Examiner l’URL, les noms, l’option `--dotfiles` et les deux chemins locaux dans
   la dernière confirmation. Le fichier et les chemins sont revérifiés avant
   de préparer les champs de la page.
4. Cloner explicitement le dépôt si nécessaire, ou ouvrir le dossier local voulu.
   Si ses configurations sont dans un sous-dossier `stow/`, ouvrir ce sous-dossier
   après clonage. Une référence ne vérifie pas l’origine GitHub d’un dossier existant.
5. Analyser les configurations. Les lignes demandées sont identifiées ; les noms
   non retrouvés restent dans le récapitulatif. Choisir ensuite **Stow** pour
   chaque configuration souhaitée et examiner son aperçu et ses sauvegardes.

L’import ne clone rien, ne lance pas d’analyse, ne crée aucun dossier ni lien et
ne modifie aucun fichier personnel ou journal de sauvegarde. Il prépare
uniquement le formulaire et les noms de référence. Le clonage conserve sa propre
confirmation ; l’activation et l’annulation conservent leurs vérifications de
plan, sauvegardes et protections contre les modifications extérieures.

Changer les dossiers locaux ou l’option invalide l’analyse, tout en conservant
les noms demandés. Changer l’URL du dépôt retire la référence chargée de la
session afin de ne pas associer les anciens choix à une autre URL. Le fichier
JSON reste disponible pour la recharger. Les références ne sont pas sauvegardées
automatiquement dans le profil utilisateur ; conserver le JSON après fermeture.

### Format et refus

Le document contient exactement `schema_version: 1`,
`kind: "minttweaks-dotfiles-reference"`, `repository_url`, une liste non vide
`packages` et le booléen `dotfiles`. Il est limité à 32 Kio et 256 noms distincts.
Les noms suivent les règles du catalogue Stow ; les dossiers exclus comme
`scripts`, `tools` et `docs` ne peuvent pas être ajoutés par l’import.

Les URL contenant des identifiants HTTPS, paramètres ou fragments, les chemins
absolus ou traversées dans les noms, les options supplémentaires, les champs
inconnus, les doublons JSON, les versions de format non prises en charge, les
liens symboliques et les fichiers spéciaux sont refusés. La source est conservée.
Un fichier modifié, un chemin devenu non sûr ou résolu vers un autre emplacement
après l’aperçu demande une nouvelle préparation. Annuler ne remplace pas les champs actuels.

Les transferts sont désactivés en simulation et utilisent la réservation commune
pour l’export et la préparation finale. Ils apparaissent dans l’historique, sans
déclencher Git, Stow, un téléchargement ou une demande de droits administrateur.

## Structure du dépôt

Chaque sous-dossier immédiat représente une configuration Stow :

```text
dotfiles/
├── bash/
│   └── .bashrc
└── kitty/
    └── .config/
        └── kitty/
            └── kitty.conf
```

Les dossiers cachés, `docs`, `scripts`, `tests`, `tools` et `node_modules` sont
exclus du catalogue. Si vos configurations sont dans `dotfiles/stow/`, ouvrez ce
sous-dossier. Un dépôt contenant directement `.bashrc` à sa racine doit d’abord
être organisé en configurations Stow. L’option **Convertir les noms dot-** permet
de traiter par exemple `bash/dot-bashrc` comme `~/.bashrc`.

Le nombre de liens affiché compte les liens existants vers les fichiers sources.
La simulation Stow reste la référence pour les liens proposés, notamment lorsque
des règles d’exclusion Stow ignorent certains fichiers. Aucun script du dépôt
n’est lancé, aucun sous-module n’est initialisé.

## Sauvegarde et annulation

- Un fichier cible existant est indiqué dans l’aperçu. Avant son remplacement,
  MintTweaks enregistre ses octets et ses permissions dans une sauvegarde privée
  datée, puis vérifie cette sauvegarde. Un lien individuel vers une autre
  configuration est sauvegardé comme lien, sans copier ni modifier sa destination.
- Les sauvegardes et journaux sont conservés dans
  `$XDG_DATA_HOME/minttweaks/dotfiles-backups/`, soit par défaut
  `~/.local/share/minttweaks/dotfiles-backups/`. Le dossier est privé (0700), les
  journaux contenant les fichiers sauvegardés sont privés (0600). Les fichiers
  de plus de 8 Mio et les sauvegardes de plus de 64 Mio sont refusés avant mutation.
- La simulation préalable utilise une cible temporaire isolée sans déplacer les
  fichiers personnels. Les exclusions Stow restent respectées : un fichier ignoré
  ne sera ni remplacé ni sauvegardé inutilement.
- **Annuler le Stow** retire les liens créés par cette activation, puis restaure
  les fichiers précédents avec leurs permissions. Sans configuration précédente,
  seuls les liens sont retirés. Les fichiers du dépôt et les sauvegardes restent
  présents ; les dossiers partagés, même devenus vides, ne sont pas supprimés.
- Les liens déjà présents avant une activation gérée sont préservés par son
  annulation. Pour une configuration installée hors de MintTweaks, le bouton retire
  uniquement les liens individuels reconnus vers ce paquet ; il n’existe alors
  aucune sauvegarde antérieure à restaurer.
- Si une cible a été remplacée manuellement, l’annulation est bloquée avant de
  retirer les autres liens. Une modification du contenu à travers un lien modifie
  toujours le fichier du dépôt : ce contenu n’est pas supprimé par l’annulation.
- Le journal reste disponible après redémarrage de MintTweaks. Il permet aussi de
  réessayer une restauration interrompue. Il faut conserver le même dossier cible
  et la même option `--dotfiles` pour retrouver l’opération.

## Précautions

- Les dossiers cibles qui sont des liens symboliques ou des fichiers sont refusés.
  MintTweaks ne déplace jamais un dossier entier comme `~/.config`. Les liens et
  fichiers spéciaux présents dans la configuration source sont aussi refusés.
- Les options explicites sont `--stow --no-folding` ; `--adopt` n’est jamais utilisé.
  Si `~/.stowrc` ou `.stowrc` dans le dossier de lancement existe, l’activation
  est refusée pour empêcher des options implicites de modifier l’opération.
  Ces fichiers ne sont ni modifiés ni supprimés par MintTweaks.
- Le plan est simulé à nouveau juste avant l’application. Évitez de modifier le
  dépôt ou les fichiers cibles pendant cette opération.
- Conservez le dépôt à son emplacement après activation : les liens en dépendent.
  Modifier un fichier à travers un lien modifie le fichier du dépôt.
- En cas d’échec d’activation, MintTweaks tente de retirer ses liens partiels et
  de restaurer les configurations sauvegardées. Si une modification extérieure
  empêche la récupération, un message indique la sauvegarde à conserver et le
  bouton d’annulation reste disponible après analyse.
- Le mode `--dry-run` ne clone rien, n’installe rien, ne crée aucun lien ni
  sauvegarde et n’effectue aucune restauration.

Les mises à jour Git et le push ne font pas partie de cette version.
La compilation et les tests avec doubles de GTK/commandes ne
remplacent pas la recette sur une session Linux Mint.
