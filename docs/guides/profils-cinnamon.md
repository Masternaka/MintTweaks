# Profils Cinnamon — capture, transfert, application et restauration

Le module lit les réglages d’apparence, les conserve dans des profils nommés,
présente les différences puis applique un profil après confirmation. Une
sauvegarde des valeurs actuelles est créée avant chaque modification. La
restauration suit le même parcours et produit sa propre sauvegarde.

## Réglages conservés

| Réglage | Schéma | Clé |
| --- | --- | --- |
| Thème Cinnamon | `org.cinnamon.theme` | `name` |
| Thème des applications | `org.cinnamon.desktop.interface` | `gtk-theme` |
| Bordures des fenêtres | `org.cinnamon.desktop.wm.preferences` | `theme` |
| Icônes | `org.cinnamon.desktop.interface` | `icon-theme` |
| Curseurs | `org.cinnamon.desktop.interface` | `cursor-theme` |
| Police de l’interface | `org.cinnamon.desktop.interface` | `font-name` |
| Police des titres | `org.cinnamon.desktop.wm.preferences` | `titlebar-font` |

Les lectures passent par `gsettings get`, avec le compte utilisateur et sans
élévation. Un schéma absent, une lecture refusée ou une valeur non reconnue
reste signalé. Une chaîne vide est conservée telle quelle. Les clés suivent les
schémas amont [Cinnamon](https://github.com/linuxmint/cinnamon/blob/master/data/org.cinnamon.gschema.xml),
[interface](https://github.com/linuxmint/cinnamon-desktop/blob/master/schemas/org.cinnamon.desktop.interface.gschema.xml.in)
et [fenêtres](https://github.com/linuxmint/cinnamon-desktop/blob/master/schemas/org.cinnamon.desktop.wm.preferences.gschema.xml.in).
Leur présence sur chaque version de Mint reste à vérifier lors des essais réels.

La capture conserve des valeurs de configuration. Elle ne certifie pas que les
thèmes ou les polices correspondants sont installés ou utilisables sur une autre
machine. La police des titres est conservée même si Cinnamon utilise la police
système pour ces titres ; le profil ne couvre pas encore ce choix. Les sept
lectures sont successives : éviter de changer les réglages dans un autre outil
pendant la capture.

## Installer Catppuccin pour Cinnamon

La carte **Catppuccin pour Cinnamon**, dans la même page, prend en charge le
dépôt [Masternaka/Cinnamon_Catppuccin](https://github.com/Masternaka/Cinnamon_Catppuccin).

1. Choisir le dossier parent du clone, ou ouvrir un dépôt déjà présent.
   Le champ **Dépôt local du thème** contient le dossier final du clone, qui ne
   doit pas encore exister. Git doit être installé pour le clonage.
2. Cliquer sur **Cloner le dépôt Catppuccin**, puis confirmer l’URL et la destination.
3. Choisir **Latte**, **Frappé**, **Macchiato** ou **Mocha**.
4. Cliquer sur **Prévisualiser l’installation du thème**. L’aperçu indique la
   source, la destination dans `~/.themes/` et la sauvegarde prévue si la variante
   est déjà installée. Confirmer pour copier les fichiers.
5. Pour l’activer, cliquer sur **Appliquer la variante au bureau**, puis confirmer
   le changement d’apparence. Les réglages précédents sont sauvegardés dans la
   liste **Restaurer l’apparence précédente**.

Les fichiers prêts à installer proviennent de `dist/Catppuccin-<variante>/`.
MintTweaks n’exécute ni l’installateur ni le générateur du dépôt. Si `dist/` est
absent ou incomplet, l’installation est refusée. L’installation copie les
fichiers du thème ; le bouton d’application change uniquement le thème du bureau
Cinnamon, en conservant les thèmes des applications, les bordures, les icônes,
les curseurs et les polices.

Avant le remplacement, la nouvelle copie est préparée et vérifiée. Une version
existante est conservée dans
`~/.themes/.minttweaks-backups/<date-UTC>-<identifiant>/Catppuccin-<variante>/` ;
son chemin est affiché dans la sortie. Aucun ancien thème n’est supprimé
automatiquement. La restauration d’apparence rétablit les réglages, pas les
fichiers d’une ancienne version du thème : ces copies restent disponibles pour
une restauration manuelle.

Les chemins symboliques et les fichiers spéciaux sont refusés. Une modification
de la source ou de la destination après l’aperçu impose une nouvelle confirmation.
L’installation se fait dans le compte utilisateur, sans droits administrateur.
Le mode `--dry-run` ne clone, ne copie et ne sauvegarde aucun thème.

## Parcours des profils

1. Ouvrir **Profils Cinnamon**, puis **Réanalyser** si nécessaire.
2. Vérifier les sept valeurs. Une capture incomplète ne peut pas être enregistrée.
3. Saisir un nom de 1 à 80 caractères, sans caractères de contrôle.
4. Choisir **Enregistrer l’apparence actuelle**. Une nouvelle capture complète
   est effectuée à cet instant pour éviter d’enregistrer un ancien affichage.
5. Retrouver le profil dans la liste et consulter ses valeurs et sa date UTC.
6. Choisir **Prévisualiser et appliquer le profil**, puis vérifier chaque ancienne
   et nouvelle valeur dans la liste défilante avant de confirmer.
7. Pour revenir en arrière, sélectionner une sauvegarde dans **Restaurer
   l’apparence précédente**, puis consulter et confirmer son aperçu.

Les profils restent consultables lorsque Cinnamon ou ses schémas ne sont pas
disponibles. L’enregistrement est désactivé en simulation et ne crée alors aucun
fichier de profil. Il utilise la réservation commune de l’application : une autre
modification en cours entraîne un refus plutôt qu’une mise en attente. Les
actions d’application et de restauration sont également désactivées en simulation.

## Export et import entre machines

Dans **Profils enregistrés**, choisir un profil puis **Exporter le profil
sélectionné…**. L’aperçu présente le JSON complet : format, identifiant, nom,
date de capture et sept valeurs. Après confirmation, choisir un nouveau fichier
`.json`. Le texte écrit correspond à l’aperçu, avec des permissions `0600`.
Un fichier existant, y compris un lien symbolique, n’est jamais remplacé.

Sur l’autre machine, choisir **Importer un profil JSON…**, sélectionner le fichier
et vérifier son nom, sa date, ses sept valeurs et le dossier local de destination.
Confirmer ajoute une copie avec un **nouvel identifiant local**. Le nom, la date de
capture originale et les valeurs sont conservés. Deux profils de même nom, même
avec la même date, restent distincts ; l’identifiant abrégé dans la liste et
l’identifiant complet dans les détails permettent de les reconnaître.

Après import, le nouveau profil est sélectionné lors de l’actualisation de la
liste. **Aucun réglage du bureau n’est appliqué par l’import.** Utiliser ensuite
l’aperçu d’application habituel, avec sauvegarde et vérifications, pour changer
l’apparence. Les thèmes, icônes et polices ne sont pas copiés ni installés par le
transfert ; ils doivent être disponibles sur la machine de destination.

Le fichier transféré utilise le format de profil `schema_version: 1`. Son nom
externe est libre ; l’identifiant contenu dans le document reste validé. L’import
refuse les formats inconnus, les valeurs ou clés non prises en charge, les
réglages incomplets, les clés JSON dupliquées, les fichiers de plus de 64 Kio,
les liens symboliques et les fichiers spéciaux. Le fichier source est conservé.
Une source modifiée après l’aperçu exige une nouvelle confirmation. Les dossiers
locaux de profils passant par des liens symboliques sont également refusés par
le parcours d’import.

L’export et l’import sont indépendants de la disponibilité des schémas Cinnamon :
un profil enregistré peut être transféré même si les réglages actuels ne sont
pas tous lisibles. Ils utilisent la réservation commune des opérations et sont
désactivés en simulation. Aucun script, commande GSettings ou téléchargement
n’est exécuté par les fonctions de transfert ; l’actualisation de la page après
import relit normalement les réglages et les catalogues.

Une collision d’identifiant ou une écriture échouée préserve les profils
existants. Si la nouvelle copie a été écrite mais ne peut pas être vérifiée par
relecture, elle est conservée et une erreur demande de recharger le catalogue
avant de réessayer. Les transferts apparaissent dans l’historique des opérations.

## Vérifications et récupération

Avant l’aperçu, les sept réglages doivent être lisibles et les clés à modifier
doivent être inscriptibles. Après confirmation, les valeurs sont relues et
comparées à celles de l’aperçu ; un changement ou une lecture impossible bloque
l’application et demande un nouvel aperçu. Un profil déjà identique ne produit
ni écriture ni sauvegarde.

La sauvegarde complète doit être écrite avant la première commande
`gsettings set`. Seules les clés différentes sont modifiées, avec le compte
utilisateur et sans privilèges administrateur. Chaque écriture est suivie d’une
relecture ; une comparaison complète est aussi effectuée à la fin. Les chaînes
sont encodées selon le [format GVariant](https://docs.gtk.org/glib/gvariant-text-format.html).

Si une commande échoue ou si la relecture ne correspond pas, le programme tente
de rétablir, en ordre inverse, les valeurs touchées par l’opération. La clé dont
l’écriture a échoué est contrôlée aussi, car une commande peut échouer après
avoir modifié sa valeur. Une valeur devenue différente à la fois de la valeur
initiale et de la valeur demandée n’est pas écrasée pendant cette récupération.
Toute récupération incomplète est signalée avec l’identifiant de la sauvegarde
et les réglages concernés. La sauvegarde reste disponible pour une restauration
explicite après correction de la cause de l’échec.

Les commandes ne forment pas une transaction GSettings globale. Un autre outil
peut encore modifier les réglages entre deux vérifications ; éviter les changements
concurrents et vérifier le résultat visuel. La restauration rétablit les valeurs
effectives enregistrées : elle ne conserve pas la distinction entre une ancienne
valeur explicitement définie et une valeur héritée des défauts du schéma. Elle
n’installe pas les thèmes ou les polices manquants.

## Format et stockage

Le dossier est `$XDG_DATA_HOME/minttweaks/cinnamon-profiles/`, ou par défaut
`~/.local/share/minttweaks/cinnamon-profiles/`. Son mode initial est `0700` ; les
fichiers sont créés en `0600`. Un dossier déjà présent garde ses permissions.

Les sauvegardes automatiques utilisent le même format et les mêmes permissions,
dans `$XDG_DATA_HOME/minttweaks/cinnamon-backups/`, ou par défaut
`~/.local/share/minttweaks/cinnamon-backups/`. Elles ne sont ni remplacées ni
supprimées automatiquement.

Chaque fichier `<identifiant>.json` contient :

- `schema_version` : entier `1` ;
- `id` : UUID sous forme de 32 caractères hexadécimaux, égal au nom du fichier ;
- `name` : nom d’affichage ;
- `captured_at` : date ISO 8601 avec fuseau horaire ;
- `settings` : les sept valeurs textuelles, indexées par `schéma/clé`.

Les noms d’affichage ne deviennent jamais des chemins. Deux profils de même nom
créent deux fichiers distincts. L’écriture prépare un fichier temporaire privé,
puis publie le document complet sans remplacer un fichier existant. Une collision
d’identifiant est refusée. Les fichiers invalides, de plus de 64 Kio, symboliques
ou d’une version inconnue sont signalés et préservés ; les autres profils restent
lisibles. Aucune suppression ni réparation automatique n’est proposée.
L’import explicite décrit plus haut ajoute une copie, sans remplacer de profil.

## Validation à effectuer sous Mint

La couverture automatisée vérifie les captures complètes et partielles, la
simulation, la conservation des valeurs vides, les permissions, les collisions,
les échecs d’écriture et les états de l’interface avec GTK simulé. Elle couvre
aussi l’aperçu périmé, les clés verrouillées, la sauvegarde préalable, les échecs
partiels, la récupération incomplète et la restauration avec sa propre sauvegarde.

Les essais de ce module, notamment les nouveaux transferts, restent à consigner.
Ajouter à la
[recette Linux Mint](../validation/linux-mint.md) : lecture des sept clés dans la
session utilisateur, concordance avec les réglages Cinnamon, enregistrement puis
réouverture, noms accentués et doublons, capture incomplète, simulation et refus
pendant une autre opération. Vérifier qu’une simple capture ne change aucun
réglage, puis appliquer un profil distinct et restaurer la sauvegarde en contrôlant
les sept valeurs et le rendu réel de Cinnamon.
