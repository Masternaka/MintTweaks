# MintTweaks

Un outil de réglages pour **Linux Mint**, inspiré d’[ArchLinux Tweak Tool](https://github.com/kirodubes/archlinux-tweak-tool) : une seule fenêtre pour les tâches système que Mint répartit entre `apt`, `systemctl`, `journalctl` et `smb.conf`.

MintTweaks utilise **Python 3 + GTK 3** : Cinnamon utilise déjà GTK 3, installé par défaut sur les versions de Mint prises en charge. L’application reprend le thème Mint-Y pour s’intégrer aux panneaux de réglages de Cinnamon.

Linux Mint fournit déjà d’excellents outils : gestionnaire de mises à jour, gestionnaire de pilotes, Timeshift et outil de sauvegarde. MintTweaks les complète avec des fonctions qui n’ont pas encore d’interface graphique dédiée.

## Fonctionnalités actuelles (v0.1)

### Entretien

- Tailles réelles du cache APT, du journal système, des miniatures et de la corbeille.
- **Aperçu de `apt-get autoremove` avant toute suppression** : vous consultez la liste des paquets, puis vous décidez.
- Nettoyage en un clic : paquets orphelins, fichiers `.deb` obsolètes, dépendances cassées, réduction du journal par taille ou ancienneté, cache des miniatures, corbeille et environnements d’exécution Flatpak inutilisés.
- Gestion prudente des noyaux : le noyau en cours d’utilisation et le plus récent ne sont jamais proposés à la suppression. Tous les paquets associés à un noyau sélectionné sont supprimés en un seul `apt-get purge`.

### Services

- Tableau filtrable de toutes les unités `*.service`, avec leur état d’exécution et leur activation au démarrage.
- Démarrage, arrêt, redémarrage, activation et désactivation, avec confirmation des actions susceptibles d’interrompre un service.
- Consultation du journal de chaque unité et option *Lire en tant qu’administrateur* lorsque le journal accessible sans privilèges est vide.
- Analyse du démarrage : résumé de `systemd-analyze`, unités les plus lentes et chaîne critique.

### Samba

- Installation de `samba`, `smbclient` et `cifs-utils` depuis l’application.
- Gestion complète des partages : création, modification, renommage et suppression, sélection de dossier, visibilité, lecture seule, accès invité, `valid users`, `write list`, masques et `force group`.
- Gestion des comptes Samba : création, changement de mot de passe, activation, désactivation et suppression. Les mots de passe passent par l’**entrée standard** de `smbpasswd`, jamais par la ligne de commande.
- Éditeur de `smb.conf` avec **validation par `testparm`**, nettoyage des doublons et sélection d’une sauvegarde à restaurer.
- Outils de service et de pare-feu : activation et démarrage de `smbd`/`nmbd`, rechargement de la configuration, autorisation de Samba dans `ufw` et liste des connexions actives.

L’interface est **traduite en français** et suit la langue du système ; `--lang fr` permet de la forcer. Voir [Langues](#langues).

## Prérequis

| Élément | Prérequis |
|---|---|
| Distribution | Linux Mint 20, 21 ou 22 (Cinnamon) |
| Exécution | `python3` ≥ 3.8, `python3-gi`, `gir1.2-gtk-3.0` (installés par défaut) |
| Privilèges | `pkexec` / polkit (`policykit-1`, installé par défaut) |
| Module Samba | `samba`, `smbclient`, `cifs-utils` (installables depuis l’application) |

## Installation

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 policykit-1
git clone https://github.com/Masternaka/MintTweaks.git
cd MintTweaks
make test          # 185 tests, sans affichage graphique
sudo make install
minttweaks
```

`make install` place le paquet et les traductions compilées dans `/usr/lib/minttweaks`, le lanceur dans `/usr/bin/minttweaks`, l’auxiliaire privilégié à côté du paquet, et l’entrée de menu, l’icône et la page de manuel dans `/usr/share`.
`sudo make uninstall` les supprime tout en conservant vos sauvegardes et journaux.

Pour lancer l’application depuis le dépôt sans l’installer : `./bin/minttweaks`.

## Préversions Debian automatiques

Chaque envoi sur `main` exécute `make test` et `make check`, construit un paquet `.deb` indépendant de l’architecture sur Ubuntu 22.04, puis publie une **préversion** GitHub dans l’onglet **Releases** du dépôt. Les pull requests vers `main` exécutent uniquement les validations. Le workflow Actions peut aussi être lancé manuellement ; la publication est limitée à `main`.

Téléchargez le `.deb` et `SHA256SUMS` de la même publication, puis exécutez :

```bash
sha256sum --ignore-missing --check SHA256SUMS
sudo apt install ./minttweaks_*_all.deb
```

Chaque construction possède une version Debian unique, par exemple `0.1.1+git12.1.abcdef123456`, et une étiquette de publication telle que `v0.1.1-build.12.1` (numéro d’exécution et tentative). Relancer tous les travaux crée une nouvelle préversion ; relancer uniquement une publication échouée téléverse à nouveau les fichiers dans la publication existante. L’application, le manuel et le paquet portent la version de construction ; la version de base du dépôt reste inchangée. Chaque publication inclut aussi une archive des sources correspondantes avec ces mises à jour de version et les sommes de contrôle SHA-256. Ses notes identifient le commit source.

Les paquets sont distribués comme **fichiers joints aux GitHub Releases** : GitHub Packages ne propose pas de registre Debian/APT. Ces préversions sont des instantanés de développement, pas des versions stables ni un dépôt APT configuré. Le workflow utilise le `GITHUB_TOKEN` automatique, avec les droits d’écriture limités au travail de publication ; aucun jeton d’accès personnel n’est nécessaire. L’automatisation démarre une fois le workflow envoyé sur `main`, si GitHub Actions est activé pour le dépôt.

## Construction d’un paquet Debian

```bash
sudo apt install debhelper dh-python devscripts
# Renseigner vos nom et adresse dans debian/control (Maintainer) et debian/changelog
dpkg-buildpackage -us -uc -b
sudo apt install ../minttweaks_0.1.1_all.deb
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

## Modèle de sécurité

- **Aucun shell.** Chaque commande est une liste d’arguments transmise à `subprocess` sans `shell=True`, ce qu’un test vérifie. Les noms de partage, chemins et noms d’unité sont validés selon des règles strictes avant toute commande.
- **Validation avant écriture.** `smb.conf` passe deux fois par `testparm`, dans l’interface et dans l’auxiliaire root. Une configuration refusée laisse la mémoire et le disque inchangés.
- **Sauvegarde avant modification.** La configuration Samba est copiée dans `~/.local/share/minttweaks/backups/` avant chaque enregistrement ; ces sauvegardes sont lisibles par l’utilisateur et restaurables depuis l’interface.
- **Aperçu des actions destructives.** `apt-get -s` simule la suppression des paquets orphelins avant toute action ; chaque noyau proposé dispose d’une case de sélection.
- **Données personnelles traitées avec votre compte.** Les miniatures et la corbeille sont nettoyées sans droits root. Les liens symboliques sont supprimés sans être suivis.
- **Refus explicites.** Le noyau en cours d’utilisation ne peut pas être purgé, la racine du système de fichiers ne peut pas être partagée et les unités inconnues ne peuvent pas être pilotées.

## Développement

```bash
make test                                  # Tests unitaires (unittest, sans pytest)
make check                                 # Syntaxe et catalogues de traduction
make translations                          # Recompiler po/*.po en .mo
MTK_DRY_RUN=1 ./bin/minttweaks               # Afficher les commandes sans les exécuter
MTK_ROOT_CMD="sudo -n" ./bin/minttweaks      # Utiliser une autre commande d’élévation
./bin/minttweaks --lang fr                   # Forcer la langue de l’interface
```

La suite de tests fonctionne aussi sur une machine sans GTK : la couche système utilise un `Runner` injectable (voir `tests/fakes.py`), et `tests/fakegi.py` simule PyGObject pour importer les modules graphiques, instancier leurs composants et leur fournir de vraies données de la couche système.

```text
minttweaks/
├── app.py                     Gtk.Application, options CLI, chargement de la langue
├── i18n.py                    Adaptateur gettext (`_`, `install`, `reset`)
├── core/
│   ├── runner.py              Command/Result et Runner injectable
│   ├── privilege.py           Élévation avec pkexec
│   ├── smbconf.py             Modèle smb.conf préservant le contenu à la réécriture
│   ├── logs.py, paths.py
├── modules/
│   ├── maintenance/           backend.py + page.py
│   ├── services/              backend.py + page.py
│   └── samba/                 backend.py + page.py
└── ui/                        window.py, widgets.py, style.css
data/                          Entrée .desktop, icône, manuel, auxiliaire mtk-root
po/                            minttweaks.pot + fr.po
tools/                         extract_strings.py, compile_mo.py
debian/                        Empaquetage avec debhelper
docs/                          Idées priorisées (ideas.md) et vision du projet
tests/                         Suite unittest, doublures et simulation de gi
```

Chaque module conserve sa logique dans `backend.py`, sans import GTK et entièrement testable, et ses composants graphiques dans `page.py`. Pour ajouter un module, écrivez sa logique système, créez une sous-classe de `Page` déclarant `page_name` / `page_title` / `page_icon`, puis ajoutez cette classe à `ui/window.py:PAGE_CLASSES`.

## Feuille de route

Les idées détaillées et priorisées figurent dans [docs/ideas.md](docs/ideas.md). La [vision et la feuille de route](docs/VISION_ET_ROADMAP.md) présentent l’orientation proposée du projet. Les prochaines pistes comprennent :

- [ ] **Diagnostic de santé du système** : un bouton pour analyser la machine et proposer des corrections.
- [ ] **Timeshift dans Entretien** : un point de restauration avant un nettoyage destructif.
- [ ] **Journal agrégé** : erreurs depuis le démarrage et messages du noyau.
- [ ] **Réglages `sysctl`** : fichier dédié, affichage de la valeur initiale et retour aux valeurs par défaut.
- [ ] Modules de **pare-feu (`ufw`)** et de **permissions Flatpak**.
- [ ] **Page matériel** : Secure Boot, santé de la batterie et micrologiciels.
- [ ] Traductions supplémentaires : le catalogue est prêt à les accueillir.

## Licence

GPL-3.0-or-later, voir [LICENSE](LICENSE).
