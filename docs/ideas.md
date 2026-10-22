# Idées d'évolution — MintTweaks

Document de travail : ce qui pourrait être ajouté, dans quel ordre, et à quel prix.
Les cases servent de suivi ; rien ici n'est engagé.

Version du document : 0.1.0 — pour toute idée retenue, ouvrir une issue et vider la
case au moment de l'implémentation.

---

## Principes

1. **Ne pas doubler Linux Mint.** Update Manager (noyaux), Driver Manager (pilotes),
   Software Sources (PPA, miroirs), Timeshift, Backup Tool, Réglages Cinnamon et
   Startup Applications couvrent déjà beaucoup. On ne les refait pas : on comble
   les trous.
2. **Le risque doit être proportionnel au gain.** Un outil de réglages qui casse un
   démarrage a tout perdu, même s'il était pratique. Lecture seule par défaut,
   écriture derrière validation + sauvegarde + confirmation.
3. **Un backend testable, un `Page` par module.** Toute nouvelle idée doit tenir
   dans `modules/<nom>/backend.py` (sans GTK, couvert par des tests avec
   `FakeRunner`) plus `page.py`.

---

## Synthèse priorisée

| # | Idée | Impact | Effort | Risque | Se branche sur |
|---|------|--------|--------|--------|----------------|
| 1 | Diagnostic « Santé du système » | ★★★ | moyen | très faible (lecture seule) | `services/`, `maintenance/` |
| 2 | Timeshift dans l'Entretien | ★★★ | petit/moyen | faible (outil officiel Mint) | `maintenance/` |
| 3 | Journal système agrégé | ★★ | petit | nul | `services/` |
| 4 | Réglages `sysctl` avec sauvegarde | ★★★ | moyen | moyen (fichier dédié, revert) | nouveau `sysctl/` |
| 5 | Pare-feu `ufw` | ★★ | petit/moyen | faible | nouveau `firewall/` |
| 6 | Permissions Flatpak | ★★ | moyen | faible | nouveau `flatpak/` |
| 7 | Matériel / « À propos » | ★★ | petit | nul | nouveau `about/` |
| 8 | Top des plus gros fichiers | ★★ | petit | nul | `maintenance/` |
| 9 | Timers systemd | ★ | petit | nul | `services/` |
| 10 | Configs résiduelles `dpkg` | ★ | petit | faible | `maintenance/` |
| 11 | Entrées de menu cassées | ★ | petit | nul | `maintenance/` |
| 12 | Nettoyage planifié (timer) | ★★ | moyen | faible | `maintenance/` |
| 13 | Test de connexion Samba | ★★ | petit | nul | `samba/` |
| 14 | Export/import de partages | ★ | petit | faible | `samba/` |
| 15 | Applications par défaut (`xdg-mime`) | ★★ | petit | faible | nouveau `defaults/` |
| 16 | Presets Cinnamon (dconf) | ★★ | moyen | moyen | nouveau `cinnamon/` |
| 17 | Journal d'actions réversible | ★★★ | gros | moyen | `core/` |

Effort indicatif : **petit** < ½ journée, **moyen** 1–2 jours, **gros** 3 jours et plus.

---

## 1. Diagnostic « Santé du système »

**Pourquoi.** C'est la fonction qui justifie de garder l'application installée : au
lieu de chercher quoi réparer, on te le dit. Entièrement en lecture seule, donc
sans risque, et elle réutilise ce qui existe déjà.

**Ce que ça fait.** Un bouton « Analyser » qui passe une série de contrôles et rend
une liste de constats classés (erreur / avertissement / info), chacun avec un
bouton d'action quand la correction est sûre.

**Contrôles envisagés.**

| Contrôle | Commande |
|---|---|
| Paquets à moitié configurés | `dpkg --audit` |
| Configs résiduelles (`rc`) | `dpkg -l` puis `apt-get purge` |
| Paquets cassés / dépendances | `apt-get check` |
| Dépôts en erreur | `apt-get update` (analyser la sortie) |
| Services en échec | `systemctl --failed` |
| Erreurs depuis le démarrage | `journalctl -p err..alert -b` |
| Espace disque | `df -h` (seuils 85 % / 95 %) |
| `fstrim.timer` inactif sur SSD | `systemctl is-enabled fstrim.timer` |
| Erreurs matérielles | `dmesg --level=err,warn` |
| Entrées `.desktop` cassées | scan `Exec=` → binaire absent |
| Noyaux installés inutiles | déjà dans l'Entretien |

**Intégration.** `modules/home/backend.py` renvoie une liste de
`Finding(severity, title, detail, action)` ; la page n'est qu'un rendu. Les
contrôles sont indépendants les uns des autres : un contrôle qui plante n'invalide
pas le rapport.

**Extras.** Bouton **« Exporter le rapport »** (texte lisible) et option `--json`
pour coller dans un ticket sans capture d'écran.

- [x] Implémenté (page Accueil, diagnostics en lecture seule ; export et option `--json` restent à faire)

---

## 2. Timeshift dans l'Entretien

**Pourquoi.** Les tâches destructrices (purge de noyaux, `autoremove`, vidage de la
corbeille) méritent un filet. Mint installe Timeshift d'office : autant s'en servir
plutôt que réinventer une sauvegarde.

**Ce que ça fait.**
- Liste des points de restauration : nom, date, taille, espace total utilisé.
- Créer un point à la demande, en supprimer un.
- Case **« créer un point de restauration avant de nettoyer »**, cochée par défaut
  pour les tâches de niveau ≥ 1.

**Technique.** `timeshift --list`, `timeshift --create --comments "…"`,
`timeshift --delete --snapshot <nom>` — tous en root via `pkexec`. Configuration
lue dans `/etc/timeshift/timeshift.json` (lecture seule, pour savoir si les
snapshots sont activés et sur quel disque).

**Pièges.** Timeshift peut être non configuré (aucune cible) : afficher alors un
message clair plutôt qu'une erreur de commande. Ne jamais proposer la création si
l'espace disque restant est sous le seuil configuré.

- [ ] Implémenter

---

## 3. Journal système agrégé

**Pourquoi.** Le module Services sait déjà afficher le journal d'une unité ; il
manque la vue « qu'est-ce qui ne va pas sur cette machine ».

**Ce que ça fait.** Un onglet avec trois vues :
- erreurs depuis le démarrage : `journalctl -p err..alert -b --no-pager` ;
- comparaison avec le boot précédent : `journalctl -b -1 -p err` ;
- messages du noyau : `dmesg --level=err,warn`.

**Effort.** Petit : trois commandes, une `TextView`, un filtre texte. Aucun risque.

- [ ] Implémenter

---

## 4. Réglages système (`sysctl`)

**Pourquoi.** C'est le cœur du métier d'un *tweak tool* : des réglages qu'on ne peut
faire aujourd'hui qu'en tapant `sysctl -w` dans un terminal.

**Réglages proposés.**

| Réglage | Clé | Défaut Mint | Intérêt |
|---|---|---|---|
| Agressivité du swap | `vm.swappiness` | 60 | 10 sur un portable avec SSD |
| Pression cache | `vm.vfs_cache_pressure` | 100 | 50 pour privilégier le cache d'inodes |
| Surveillance de fichiers | `fs.inotify.max_user_watches` | 65536 | 524288 pour les devs (`ENOSPC`) |
| Instances inotify | `fs.inotify.max_user_instances` | 128 | 512 avec beaucoup de conteneurs |
| Fichiers ouverts | `fs.file-max` | élevé | rarement utile |

**Règles de sécurité.**
- Écrire **uniquement** dans `/etc/sysctl.d/99-minttweaks.conf`, jamais dans
  `/etc/sysctl.conf` (qui appartient au système).
- Afficher la valeur d'origine à côté de chaque champ.
- Bouton « revenir au défaut » = suppression de la ligne, puis
  `sysctl --system`.
- Validation : entier positif dans une plage plausible, refus sinon.

**Bonus.** Un onglet « mémoire » : état du swap/zram (`zramctl`, `swapon --show`) et
création d'un fichier d'échange, utile sur les machines à 4 Go.

- [ ] Implémenter

---

## 5. Pare-feu (`ufw`)

**Pourquoi.** `ufw` est installé mais **désactivé** par défaut sur Mint, et son
interface graphique (Gufw) n'est pas installée d'office. C'est un trou réel, et on
a déjà le bouton « autoriser Samba » dans le module Samba.

**Ce que ça fait.** État du pare-feu, tableau des règles
(`ufw status numbered`), ajout d'une règle (port / service / protocole),
suppression par numéro (`ufw delete <n>`), activation/désactivation avec
confirmation.

**Piège.** Activer `ufw` coupe les connexions entrantes : avertir explicitement
qu'un serveur SSH entrant doit être autorisé **avant** l'activation.

- [ ] Implémenter

---

## 6. Permissions Flatpak

**Pourquoi.** Flathub est déjà configuré sur Mint, donc l'intérêt n'est pas
l'installation mais **les permissions** : il faut aujourd'hui installer Flatseal.

**Ce que ça fait.** Par application : liste des permissions effectives
(`flatpak override --show <app>`), et bascules sur les plus parlantes —
accès au `home`, au système de fichiers, réseau, sockets X11/Wayland, appareils,
variables d'environnement. Écriture via `flatpak override --user --nofilesystem=…`.

**Piège.** Distinguer les permissions globales (`--user`) de celles de l'app, et
proposer un « reset » (`flatpak override --user --reset <app>`).

- [ ] Implémenter

---

## 7. Matériel / « À propos »

**Pourquoi.** Alimente le rapport de diagnostic et répond à la question « c'est quoi
cette machine » sans ouvrir trois terminaux.

**Contenu.** Version de Linux Mint et de Cinnamon, noyau, CPU, RAM, GPU, disques,
état Secure Boot (`mokutil --sb-state`), santé de la batterie
(`energy_full` vs `energy_full_design` dans `/sys/class/power_supply/`), SMART si
`smartmontools` est présent.

**Effort.** Petit, lecture seule.

- [ ] Implémenter

---

## 8. Top des plus gros fichiers

**Pourquoi.** « Qu'est-ce qui remplit mon disque ? » est la question la plus
fréquente, et aucun outil Mint ne la traite simplement.

**Ce que ça fait.** Les 20 plus gros fichiers de `~` et les 10 plus gros
sous-dossiers, avec bouton « révéler dans Nemo ». Balayage en profondeur limitée
(3–4 niveaux), dans un thread, avec annulation.

**Piège.** Ne jamais suivre les liens symboliques (déjà le cas dans
`maintenance/backend.py`) et ignorer les montages réseau.

- [ ] Implémenter

---

## 9. Timers systemd

**Pourquoi.** Personne ne sait ce qui tourne périodiquement sur sa machine depuis
que cron a été remplacé.

**Ce que ça fait.** `systemctl list-timers --all` dans un tableau (prochaine
exécution, dernière exécution, unité), avec accès au journal du timer.

- [ ] Implémenter

---

## 10. Configs résiduelles `dpkg`

**Pourquoi.** Les fichiers de configuration restent après une désinstallation, et
`apt` ne les liste jamais.

**Ce que ça fait.** `dpkg -l` filtré sur l'état `rc`, avec purge groupée après
confirmation. Peut être un bouton du diagnostic plutôt qu'une page.

- [ ] Implémenter

---

## 11. Entrées de menu cassées

**Pourquoi.** Un `.desktop` qui pointe vers un binaire désinstallé laisse une icône
morte dans le menu, sans explication.

**Ce que ça fait.** Scanner `/usr/share/applications`, `/usr/local/share/applications`
et `~/.local/share/applications`, vérifier que la cible de `Exec=` existe, proposer
la suppression (ou le masquage) des entrées fautives de l'espace utilisateur.

- [ ] Implémenter

---

## 12. Nettoyage planifié

**Pourquoi.** L'Entretien ne sert que si on y pense.

**Ce que ça fait.** Une case « exécuter ce nettoyage tous les mois » qui installe
une unité `systemd` utilisateur (`minttweaks-cleanup.timer`) rejouant les tâches
choisies, avec un journal consultable.

**Piège.** Les tâches root ne peuvent pas passer par un timer utilisateur : soit
tout en `--user` (miniatures, corbeille), soit une unité système avec les
autorisations correspondantes. Commencer par le périmètre utilisateur.

- [ ] Implémenter

---

## 13. Test de connexion Samba

**Pourquoi.** On configure un partage, on l'annonce, et on découvre que le client
n'a pas accès.

**Ce que ça fait.** Depuis la page Samba : se connecter à `localhost` avec
`smbclient -L localhost` puis lister un partage donné, afficher le résultat brut.
Permet de valider avant de crier victoire.

**Piège.** Ne jamais passer de mot de passe en argument : utiliser
`--authentication-file` ou l'entrée standard.

- [ ] Implémenter

---

## 14. Export / import de partages

**Pourquoi.** Rejouer une configuration Samba sur une autre machine, ou la mettre
sous Git sans embarquer tout `smb.conf`.

**Ce que ça fait.** Export JSON des sections « partages » (pas de `[global]`, pas de
secrets), import avec aperçu et validation `testparm` avant écriture.

- [ ] Implémenter

---

## 15. Applications par défaut

**Pourquoi.** Changer le navigateur ou le client mail par défaut est
étonnamment peu évident sur Mint, et `xdg-mime` n'a pas d'interface.

**Ce que ça fait.** Tableau des catégories courantes (navigateur, mail, terminal,
éditeur de texte, lecteur PDF, images) avec
`xdg-mime query default <type>` et `xdg-settings set default-web-browser …`.

- [ ] Implémenter

---

## 16. Presets et sauvegarde Cinnamon

**Pourquoi.** Les Réglages Cinnamon font très bien l'édition unitaire ; ce qui
manque, c'est **sauvegarder/restaurer/partager** une configuration.

**Ce que ça fait.** Export `dconf dump /org/cinnamon/` vers un fichier daté dans le
dossier de sauvegardes de MintTweaks, restauration avec aperçu des différences, et
deux ou trois presets (bureau sobre, portable, multi-écrans).

**Piège.** `dconf reset -f /org/cinnamon/` est brutal : toujours proposer l'export
avant le reset.

- [ ] Implémenter

---

## 17. Journal d'actions réversible

**Pourquoi.** Toutes les écritures passent déjà par un entonnoir unique
(`save_document`, `_apply_conf_change`). Enregistrer chaque action et son inverse
permettrait un vrai « annuler la dernière opération » — rare dans ce genre d'outil,
et c'est ce qui change la confiance qu'on accorde à l'application.

**Ce que ça fait.** Un fichier `~/.local/share/minttweaks/actions.log` (JSON
lines) listant les N dernières opérations, et une action « annuler » qui restaure
la sauvegarde correspondante.

**Effort.** Gros : il faut définir un inverse pour chaque type d'écriture, et les
opérations `apt` ne sont pas réversibles (on peut seulement réinstaller). Commencer
par le périmètre fichier (`smb.conf`, `sysctl.d`) qui est déjà sauvegardé.

- [ ] Implémenter

---

## À éviter (et pourquoi)

| Idée | Raison |
|---|---|
| Gestionnaire de thèmes / icônes / polices | Réglages Cinnamon le fait mieux ; seul angle utile : installer un thème tiers depuis un zip |
| Gestion des PPA et des miroirs | `mintsources` (Logiciels → Dépôts) couvre déjà, test de vitesse inclus |
| Noyaux mainline | Update Manager → Noyaux existe et gère la cohérence |
| Sauvegarde de fichiers | Backup Tool + Timeshift |
| Édition de `/etc/fstab` | Trop de façons de rendre une machine non démarrable ; en **audit** lecture seule, en revanche, oui |
| Édition de la configuration GRUB | Idem ; un simple réglage de délai reste acceptable, pas plus |
| Édition de `sudoers` | Un fichier invalide casse `sudo`. Un audit (« lignes NOPASSWD détectées ») suffit |
| Gestionnaire de paquets complet | `mintinstall` et Synaptic existent |

---

## Ordre suggéré

1. **Diagnostic** — le plus utile, et il réutilise l'existant.
2. **Timeshift dans l'Entretien** — le plus rapide, et il sécurise tout le reste.
3. **Journal agrégé** — une demi-journée, complète le module Services.
4. **`sysctl`** — le vrai « tweak », avec sauvegarde et retour au défaut.
5. **Pare-feu** puis **Flatpak** — deux modules courts, très concrets.

L'étape 1 et l'étape 2 se combinent bien : le diagnostic peut proposer « créer un
point de restauration » avant de lancer une correction.
