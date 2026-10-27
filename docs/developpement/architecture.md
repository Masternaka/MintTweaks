# Développement et architecture

## Construction d’un paquet Debian

```bash
sudo apt install debhelper dh-python devscripts
# Renseigner vos nom et adresse dans debian/control (Maintainer) et debian/changelog
dpkg-buildpackage -us -uc -b
sudo apt install ../minttweaks_0.1.3_all.deb
```

L’empaquetage reste simple : `debian/rules` appelle le même `make install` qu’une installation depuis les sources, ce qui permet de maintenir une seule organisation des fichiers. `make check` vérifie la syntaxe et les traductions ; `make test` contrôle notamment la structure de l’empaquetage depuis toute machine, sans nécessiter `dpkg` :

- présence de tous les fichiers attendus par debhelper et de recettes avec tabulations dans le fichier exécutable `debian/rules` ;
- déclaration de `python3-gi`, `gir1.2-gtk-3.0` et `policykit-1` dans `debian/control` ;
- correspondance de la version du journal des modifications avec `minttweaks/__init__.py` ;
- correspondance des champs `Exec`/`Icon` de l’entrée de menu avec les fichiers installés par le Makefile ;
- suppression par `make uninstall` de ce qu’installe `make install`.

## Langues

Les chaînes sources sont en anglais ; le français est fourni sous forme de catalogue compilé.

```bash
make pot            # Régénérer po/minttweaks.pot depuis les sources
make translations   # Compiler po/*.po dans minttweaks/locale/<lang>/LC_MESSAGES/
make check          # Échouer si le modèle est périmé ou une chaîne non traduite
```

Pour ajouter une langue, copiez `po/fr.po` vers `po/de.po`, traduisez les chaînes, ajoutez le code de langue à `LANGUAGES` dans le `Makefile`, puis exécutez `make translations`. `--lang de` force cette langue pour une exécution et `MTK_LOCALEDIR` indique un répertoire de catalogues.

Deux règles facilitent la maintenance :

- chaque chaîne visible est enveloppée dans `_()` ; `tools/extract_strings.py` refuse les f-strings, car elles ne peuvent pas être extraites ;
- les chaînes créées à l’importation, dans le registre des tâches, conservent le msgid anglais et sont traduites à l’accès pour utiliser le catalogue chargé au démarrage.

Le **panneau de sortie reste en anglais** : il retranscrit les commandes et les sorties de `apt` et `testparm`. Sa traduction compliquerait la lecture des rapports de bogues.

## Fonctionnement des privilèges

MintTweaks s’exécute avec votre compte. Il ne conserve jamais les droits root et ne lance jamais de shell. Les actions nécessitant des droits d’administration passent par `pkexec`, avec la boîte de dialogue polkit habituelle de Cinnamon.

Le remplacement de `/etc/samba/smb.conf` passe par l’auxiliaire `data/mtk-root`, dont le rôle est limité à ce fichier :

- il accepte uniquement un fichier ordinaire appartenant à l’utilisateur appelant, de moins de 1 Mio, dont le contenu ressemble à un `smb.conf` ;
- il exécute `testparm` **en tant que root** avant toute modification ; l’interface valide également le fichier en amont, ce qui permet normalement de rejeter une configuration incorrecte avant de demander un mot de passe ;
- il copie le fichier courant dans `/var/backups/samba/smb.conf.<timestamp>`, conserve les 20 dernières sauvegardes et impose `root:root 0644` au résultat ;
- il recharge `smbd` dans le même appel privilégié : une seule autorisation est nécessaire par enregistrement.

Les extensions Firefox passent par l’auxiliaire `data/mtk-firefox`, limité à `/etc/firefox/policies/policies.json` :

- il n’accepte que les identifiants du catalogue et une politique `normal_installed` pointant vers le téléchargement officiel `addons.mozilla.org` ;
- il fusionne la sélection dans le fichier existant, sans toucher aux autres politiques ni aux entrées qu’il n’a pas écrites ;
- il sauvegarde le fichier courant dans `/var/backups/minttweaks/` et force `root:root 0644`.

## Modèle de sécurité

- **Aucun shell.** Chaque commande est une liste d’arguments transmise à `subprocess` sans `shell=True`, ce qu’un test vérifie. Les noms de partage, chemins et noms d’unité sont validés selon des règles strictes avant toute commande.
- **Validation avant écriture.** `smb.conf` passe deux fois par `testparm`, dans l’interface et dans l’auxiliaire root. Une configuration refusée laisse la mémoire et le disque inchangés.
- **Sauvegarde avant modification.** La configuration Samba est copiée dans `~/.local/share/minttweaks/backups/` avant chaque enregistrement ; ces sauvegardes sont lisibles par l’utilisateur et restaurables depuis l’interface.
- **Aperçu des actions destructives.** `apt-get -s` simule la suppression des paquets orphelins avant toute action ; chaque noyau proposé dispose d’une case de sélection.
- **Installation d’extensions depuis la source officielle.** Firefox télécharge lui-même les modules depuis `addons.mozilla.org` ; MintTweaks n’installe jamais un fichier XPI fourni par l’utilisateur.
- **Données personnelles traitées avec votre compte.** Les miniatures et la corbeille sont nettoyées sans droits root. Les liens symboliques sont supprimés sans être suivis.
- **Refus explicites.** Le noyau en cours d’utilisation ne peut pas être purgé, la racine du système de fichiers ne peut pas être partagée et les unités inconnues ne peuvent pas être pilotées.

## Développement

```bash
make test                                  # Tests unitaires (unittest, sans pytest)
make check                                 # Syntaxe et catalogues de traduction
make translations                          # Recompiler po/*.po en .mo
MTK_DRY_RUN=1 ./bin/minttweaks               # Afficher les commandes sans les exécuter
./bin/minttweaks --dry-run                  # Même simulation, nettoyages Python compris
MTK_ROOT_CMD="sudo -n" ./bin/minttweaks      # Utiliser une autre commande d’élévation
./bin/minttweaks --lang fr                   # Forcer la langue de l’interface
```

La suite de tests fonctionne aussi sur une machine sans GTK : la couche système utilise un `Runner` injectable (voir `tests/fakes.py`), et `tests/fakegi.py` simule PyGObject pour importer les modules graphiques, instancier leurs composants et leur fournir de vraies données de la couche système.

La [recette Linux Mint](../validation/linux-mint.md) décrit la construction et
l’installation réelles du paquet, les essais avec GTK et les scénarios manuels.
Son [modèle de compte rendu](../validation/compte-rendu.md) permet
de consigner les preuves sans confondre ces essais avec les tests simulés.

La simulation empêche aussi le vidage de la corbeille et le nettoyage des miniatures réalisés directement en Python. Les commandes de diagnostic sont simulées elles aussi : les listes affichées en simulation ne constituent donc pas une analyse réelle de la machine. Les journaux de l’application et ses fichiers temporaires peuvent toujours être écrits.

Une fenêtre de simulation porte une indication dédiée et utilise une instance distincte : lancer `--dry-run` ne réactive pas une fenêtre normale déjà ouverte.

La nouvelle vérification d’`autoremove` réduit le risque d’un aperçu périmé, mais elle ne verrouille pas APT entre simulation, autorisation polkit et exécution. Évitez de modifier les paquets avec un autre outil pendant cette opération.

Les modifications des modules, des configurations utilisateur et de la progression du parcours utilisent une réservation commune, conservée jusqu’au traitement du résultat par l’interface. Une seconde modification est refusée, sans mise en attente ; les diagnostics et consultations restent disponibles. La barre d’état indique l’opération en cours. La fermeture de la fenêtre et le raccourci Quitter attendent la fin de l’opération.

Les commandes en continu ont un délai de 30 minutes par défaut, ramené à 2 minutes pour les commandes de service. Le délai couvre aussi les commandes silencieuses et les sorties sans fin de ligne. Une commande ordinaire qui dépasse ce délai est arrêtée avec son groupe de processus. Une commande administrative n’est pas interrompue brutalement : le dépassement est signalé dans la sortie, la réservation reste active et la commande reste surveillée jusqu’à sa fin. Son résultat signale ensuite le dépassement avec le code 124, même si la commande a finalement terminé son travail. Ces délais concernent `stream()` ; les commandes exécutées par `run()` conservent leurs délais existants.

## Organisation des sources

| Dossier | Rôle |
| --- | --- |
| `minttweaks/core/` | Commandes, privilèges, chemins, journaux, transactions de fichiers et modèle Samba |
| `minttweaks/modules/` | Logique et interface des neuf modules |
| `minttweaks/ui/` | Fenêtre, composants communs et style GTK |
| `bin/` | Lanceur de l’application |
| `data/` | Auxiliaires privilégiés, entrée de menu, icône et manuel |
| `po/` | Modèle gettext et traductions sources |
| `tools/` | Extraction/compilation gettext et préparation des publications |
| `tests/` | Tests unittest, doubles de commandes et simulation de GTK |
| `debian/` | Sources de construction du paquet Debian |
| `.github/` | Workflow de validation/publication et consignes de commit |

Chaque module sépare sa logique système de GTK. Les modules simples utilisent
`backend.py` et `page.py` ; le terminal répartit ses responsabilités entre
`catalog.py`, `integrations.py`, `configuration.py`, `status.py`, `transfer.py`
et `controls.py`. Déclarer les nouvelles pages dans `ui/window.py:PAGE_CLASSES`.
Les noms de packages, les points d’entrée et les fichiers installés restent
stables : ne pas les déplacer pour une réorganisation documentaire.
