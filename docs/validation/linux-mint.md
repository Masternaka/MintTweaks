# Recette de validation sous Linux Mint

**État : préparée, non exécutée.** Aucun résultat Linux réel n’est établi par ce document.

Cette recette couvre un candidat précis, de ses sources à son paquet installé.
Elle ne publie ni commit, ni tag, ni Release. La décision de publication suit la
[procédure de version](../developpement/publication.md).

## Environnement et preuves

Utiliser une VM jetable avec une session graphique Cinnamon et un compte de test
administrateur. Les données, partages, politiques Firefox et paquets de cette VM
doivent pouvoir être modifiés pendant les essais. Conserver un état initial de la
VM dans l’hyperviseur pour pouvoir recommencer les scénarios.

Choisir d’abord une version de Mint à tester et noter sa version exacte. Les
familles Mint 20, 21 et 22 annoncées dans le README sont des cibles à confirmer
séparément : un essai sur une seule version ne valide pas les autres.

Copier le [modèle de compte rendu](compte-rendu.md) dans le
dossier de résultats choisi. Renseigner les identifiants du candidat, les
commandes, leurs codes de sortie, les captures et les anomalies. Les valeurs
autorisées sont **non effectué**, **réussi**, **échoué**, **bloqué**, **sans objet**.

Dans un terminal de la VM, relever :

```bash
cat /etc/os-release
uname -r
dpkg --print-architecture
python3 --version
cinnamon --version
printf 'Session : %s\nBureau : %s\n' "$XDG_SESSION_TYPE" "$XDG_CURRENT_DESKTOP"
```

## 1. Transférer le candidat exact

Depuis le dossier du projet sur le Mac, créer une archive du répertoire de travail.
Elle doit inclure les nouveaux fichiers non encore suivis par Git. Une archive de
`HEAD` seul ne contiendrait pas les corrections locales en cours.

```bash
git rev-parse HEAD
git status --short
tar --exclude='./.git' --exclude='./dist' \
    --exclude='./.venv' --exclude='__pycache__' \
    -czf /tmp/minttweaks-candidat.tar.gz .
shasum -a 256 /tmp/minttweaks-candidat.tar.gz
```

Noter le commit de base, la présence des modifications locales et le SHA-256 de
l’archive. Transférer l’archive dans `/tmp/` de la VM par le mécanisme de partage
de l’hyperviseur. Vérifier que le SHA-256 est identique avant extraction.

```bash
sha256sum /tmp/minttweaks-candidat.tar.gz
mkdir -p "$HOME/minttweaks-recette/source"
tar -xzf /tmp/minttweaks-candidat.tar.gz -C "$HOME/minttweaks-recette/source"
cd "$HOME/minttweaks-recette/source"
```

## 2. Construire et installer le paquet

Installer les outils de construction et les dépendances graphiques dans la VM :

```bash
sudo apt update
sudo apt install build-essential debhelper dh-python devscripts \
    python3-gi gir1.2-gtk-3.0 policykit-1
make test
make check
dpkg-buildpackage -us -uc -b
```

Chaque commande doit réussir avant de poursuivre. Si une dépendance déclarée
dans `debian/control` est indisponible pour cette version de Mint, noter un
blocage de compatibilité ; ne pas contourner la dépendance pour déclarer le test
réussi. Sous Linux avec `dpkg`, le test de classement des versions Debian ne
doit plus être ignoré.

```bash
mtk_candidate_version=$(python3 -c 'from minttweaks import __version__; print(__version__)')
dpkg-deb -f "../minttweaks_${mtk_candidate_version}_all.deb" Package Version Architecture
dpkg-deb --contents "../minttweaks_${mtk_candidate_version}_all.deb"
sha256sum "../minttweaks_${mtk_candidate_version}_all.deb" > ../SHA256SUMS
sha256sum --check ../SHA256SUMS
sudo apt install "../minttweaks_${mtk_candidate_version}_all.deb"
```

Attendu : paquet `minttweaks`, version du candidat, architecture `all` ; lanceur,
auxiliaires, icône, manuel et traduction française présents dans le paquet.
Conserver le `.deb` et sa somme de contrôle avec les preuves.

Une archive extraite n’est pas un checkout Git : `git diff --check` ne peut pas y
servir de validation. Ce contrôle est à effectuer sur le répertoire original.

## 3. Vérifier l’application installée avec le vrai GTK

Quitter le dossier des sources pour éviter d’importer accidentellement ce dossier.

```bash
cd "$HOME"
command -v minttweaks
dpkg-query -W -f='${Version}\n' minttweaks
minttweaks --version
PYTHONPATH=/usr/lib/minttweaks /usr/bin/python3 -c \
    'import minttweaks; print(minttweaks.__file__); print(minttweaks.__version__)'
G_DEBUG=fatal-criticals minttweaks --lang fr
```

Attendu : lanceur installé dans `/usr/bin`, module sous `/usr/lib/minttweaks`,
versions cohérentes ; aucun arrêt sur une erreur critique GTK. Ouvrir les neuf
pages, actualiser chacune et vérifier leurs données. Fermer l’application, puis
recommencer avec `--lang en`. Relever les erreurs du terminal et du journal.

Les tests habituels utilisent des doublures GTK : leur réussite ne remplace pas
cet essai. Vérifier aussi le lancement depuis le menu Cinnamon, la lisibilité
avec les thèmes clair et sombre, les listes longues, le défilement et le clavier.

## 4. Exécuter les scénarios

Pour les fichiers témoins, utiliser uniquement le compte de test de la VM.

### Simulation

```bash
mkdir -p "$HOME/.cache/thumbnails"
printf 'Témoin miniatures\n' > "$HOME/.cache/thumbnails/minttweaks-recette-temoin"
printf 'Témoin corbeille\n' > "$HOME/minttweaks-recette-temoin.txt"
gio trash "$HOME/minttweaks-recette-temoin.txt"
```

Repérer le fichier témoin dans la corbeille avant de poursuivre. Lancer
`minttweaks --dry-run`, vider la corbeille et nettoyer les miniatures depuis
l’interface. Les deux témoins doivent rester présents et inchangés. Recommencer
avec `MTK_DRY_RUN=1 minttweaks`. Avec une fenêtre normale déjà ouverte, le lancement
simulé doit ouvrir une instance distincte portant l’indication de simulation.
Les contrôles simulés ne doivent pas être annoncés comme réussis.

### Service de test et opérations entre pages

Créer uniquement ce service temporaire dans la VM :

```bash
sudo tee /run/systemd/system/minttweaks-recette.service >/dev/null <<'UNIT'
[Unit]
Description=Service temporaire de recette MintTweaks

[Service]
Type=oneshot
ExecStart=/bin/sleep 15
TimeoutStartSec=180
RemainAfterExit=yes
UNIT
sudo systemctl daemon-reload
```

Le service disparaîtra après redémarrage. Dans Services, le démarrer depuis
MintTweaks et accepter polkit. Pendant les 15 secondes d’exécution, tenter une
modification dans Samba ou Firefox : elle doit être refusée sans exécution.
Essayer la fermeture et Ctrl+Q : la fenêtre doit rester ouverte. Les consultations
doivent rester possibles. À la fin, l’indicateur doit disparaître et une nouvelle
opération doit être possible. Tester ensuite l’arrêt de ce service uniquement.

Pour vérifier le dépassement administratif, remplacer `sleep 15` par `sleep 130`
dans ce même fichier, recharger systemd et redémarrer le service depuis l’interface.
Après le délai de 120 secondes, la sortie doit signaler le dépassement et la
surveillance doit continuer jusqu’à la fin. Aucune autre modification ni fermeture
normale ne doit être autorisée entre-temps. Le résultat final porte le code 124,
même si la commande a fini son travail. Ne pas utiliser une installation APT pour
provoquer volontairement ce dépassement.

### Tableau de vérification

| ID | Action dans la VM | Résultat attendu |
| --- | --- | --- |
| M01 | Annuler une demande polkit sur le service temporaire | Échec explicite, aucun changement demandé, interface utilisable ensuite |
| M02 | Actualiser Accueil | Résumé chargé ; contrôles indisponibles comptés séparément des réussites |
| M03 | Déclencher les deux accès à la suppression des paquets orphelins, puis annuler | Même liste complète et défilante ; aucune suppression |
| M04 | Confirmer une suppression après inspection de la liste, uniquement dans la VM | Résultat APT visible ; nouvelle analyse ; si le plan a changé ou échoué, suppression refusée |
| M05 | Vider la corbeille et nettoyer les miniatures en mode normal | Seuls les témoins et données de test concernés sont nettoyés |
| M06 | Inspecter les noyaux proposés | Noyau courant et plus récent protégés ; lecture du noyau courant vérifiée |
| M07 | Purger un ancien noyau réellement disponible, puis redémarrer la VM | Paquets attendus supprimés et système toujours démarrable ; sans ancien noyau, noter « sans objet » |
| M08 | Lire le journal d’un service et l’analyse du démarrage | Données affichées ; résultats partiels ou échecs explicités |
| M09 | Lors d’un véritable échec de lecture, réactualiser Services | Anciennes données signalées ; actions désactivées jusqu’à une lecture réussie |
| M10 | Installer Samba depuis MintTweaks si absent | Résultat APT explicite, module utilisable après réussite |
| M11 | Créer, modifier puis supprimer un partage de dossier de test | `testparm` valide la configuration ; autres sections préservées ; sauvegarde créée |
| M12 | Soumettre une configuration Samba invalide, puis restaurer une sauvegarde | Rejet sans écriture pour la configuration invalide ; restauration vérifiée par lecture du fichier et `testparm` |
| M13 | Gérer uniquement un compte Samba de test | Mot de passe et état du compte cohérents ; aucun mot de passe dans la sortie ou les journaux |
| M14 | Installer une extension du catalogue Firefox natif, puis redémarrer Firefox | Politique écrite avec sauvegarde ; extension réellement installée après redémarrage |
| M15 | Retirer la politique MintTweaks | Autres politiques préservées ; extension déjà installée conservée |
| M16 | Désinstaller puis réinstaller le paquet | Lanceur retiré puis fonctionnel ; sauvegardes et journaux utilisateur conservés |
| M17 | Enregistrer deux profils Cinnamon distincts, appliquer l’un puis restaurer la sauvegarde | Aperçu fidèle ; sauvegarde avant chaque changement ; sept valeurs vérifiées et rendu inspecté ; aucune modification sans confirmation |
| M18 | Modifier un réglage depuis les préférences Cinnamon pendant qu’un aperçu est ouvert, puis confirmer | Application refusée ; nouvelle lecture et nouvelle confirmation nécessaires |
| M19 | Examiner les erreurs de récupération et les fichiers de sauvegarde après un échec reproductible | Erreur explicite, sauvegarde conservée ; ne pas assimiler la réussite des tests simulés à un essai réel de panne |
| M20 | Choisir un parcours dans l’assistant et ouvrir chaque module | Récapitulatif lisible ; aucune modification exécutée par la seule navigation |
| M21 | Marquer une étape vérifiée, une autre à reprendre avec une note, puis rouvrir l’application | Reprise à l’étape non vérifiée ; état et note conservés ; aucune validation implicite |
| M22 | Essayer l’assistant en simulation et vérifier une petite fenêtre | Aucune progression écrite ; navigation utilisable ; raccourcis de l’accueil répartis sur plusieurs lignes |
| M23 | Configurer les sources officielles Helium et Brave, puis installer leurs paquets depuis Logiciels natifs | Origine et suite attendues ; aperçu complet ; paquets et versions natifs vérifiés puis navigateurs réellement lancés |
| M24 | Vérifier Zen avec puis sans dépôt central disponible et configuré | Installation proposée uniquement si le candidat attendu existe ; mention du paquet non officiel ; lancement vérifié après installation |
| M25 | Annuler polkit, simuler une panne réseau ou changer le plan avant confirmation | Aucun faux succès ; état APT réactualisé ; aucune suppression automatique après une installation partielle |
| M26 | Ouvrir un parcours enregistré au format 1, puis ajouter Logiciels natifs | Sélections et notes conservées ; nouvelle étape non sélectionnée initialement ; format 2 écrit à la sauvegarde explicite |

La comparaison APT avant suppression ne verrouille pas l’état des paquets jusqu’à
l’exécution. Noter cette limite dans le compte rendu. Si un scénario d’échec ou
de changement de plan ne peut pas être reproduit, le noter **non effectué** ; les
tests unitaires correspondants restent des preuves distinctes.

Pour M11 et M12, vérifier le fichier réel `/etc/samba/smb.conf` et les sauvegardes
sous `~/.local/share/minttweaks/backups/` et `/var/backups/samba/`. Pour M14 et M15,
vérifier `/etc/firefox/policies/policies.json`, les sauvegardes sous
`/var/backups/minttweaks/` et `about:policies` dans Firefox.

## 5. Conclure la recette

Joindre les sorties de construction, les captures représentatives et les erreurs
pertinentes du fichier `~/.local/share/minttweaks/logs/minttweaks.log`. Relire les
preuves avant de les partager pour retirer les données personnelles éventuelles.

Tout échec d’installation, perte de données, erreur critique GTK, contournement du
mode simulation ou défaut des protections de suppression bloque la validation du
candidat. Décrire les scénarios non effectués et les limites restantes ; ne pas
cocher la validation Mint dans la feuille de route sur la seule base des tests
automatisés. Après une correction, reconstruire un candidat identifié et rejouer
les scénarios concernés.

La recette de distribution distante (GitHub Actions, téléchargement et contrôle
des pièces jointes) reste distincte. Aucun accès distant ni publication n’est
nécessaire pour préparer cette recette locale.

## Shells et terminaux

Effectuer ces essais sur une VM avec instantané, puis consigner les résultats.

| ID | Essai | Résultat attendu |
| --- | --- | --- |
| T01 | Ouvrir la page en français puis en anglais, petite fenêtre et thème sombre | Neuf pages accessibles, huit onglets défilants utilisables dont le catalogue de 32 outils et textes lisibles |
| T02 | Sélectionner Kitty et Alacritty absents, annuler l’aperçu puis installer | Annulation sans installation ; plan complet, polkit puis versions vérifiées |
| T03 | Examiner Starship sans candidat APT | Indisponibilité explicite et guide officiel accessible ; aucune exécution de script distant |
| T04 | Choisir un shell installé présent dans `/etc/shells`, annuler puis confirmer | Ancienne valeur sauvegardée, compte courant seul modifié, nouvelle session nécessaire |
| T05 | Se reconnecter, contrôler le shell puis restaurer le précédent et se reconnecter | Shells conformes aux confirmations ; terminaux existants non interrompus |
| T06 | Activer Starship dans chaque shell installé et ouvrir un nouveau terminal | Invite dossier/Git/caractère, alias conservés, sauvegarde et bloc uniques |
| T07 | Retirer le bloc Starship et ouvrir un nouveau terminal | Bloc retiré, autres réglages conservés |
| T08 | Créer les profils clair et sombre de Kitty et Alacritty, changer police et taille | Entrées MintTweaks fonctionnelles, réglages visibles ; configurations normales conservées |
| T09 | Restaurer une sauvegarde depuis la page | Aperçu puis nouvelle sauvegarde ; fichiers et permissions rétablis, fichiers précédemment absents retirés |
| T10 | Modifier un fichier pendant l’aperçu ou occuper la réservation dans un autre module | Écriture refusée et contrôles utilisables après le message |
| T11 | Essayer la page en `--dry-run` | Aucune écriture, aucun changement de compte ni installation |
| T12 | Reprendre une ancienne progression Après installation de format 1 ou 2 | Sélections, notes et vérifications conservées ; nouvelle étape terminal non sélectionnée |

Tester si possible Alacritty antérieur à 0.13 (YAML) et une version récente
(TOML). Ne pas déclarer les deux formats validés sur la base d’une seule version.

### Compléments de recette pour le catalogue d’utilitaires

| ID | Essai | Résultat attendu |
| --- | --- | --- |
| U01 | Parcourir les six catégories et les liens du catalogue | Descriptions et exemples lisibles, documentation du bon projet ; aucun exemple exécuté |
| U02 | Choisir les outils de départ sur une machine avec quelques outils installés | Seuls les essentiels absents et disponibles sont cochés ; aucune installation immédiate |
| U03 | Installer fd, bat, ripgrep, Neovim et delta si disponibles, puis réactualiser | Bons paquets APT ; détection de fdfind, batcat, rg, nvim et delta sans réinstallation proposée |
| U04 | Installer les extensions Zsh et consulter leur état | Paquets détectés ; activation avec aperçu et sauvegarde dans Zsh, non-applicabilité signalée dans Bash/Fish |
| U05 | Consulter un outil sans candidat, puis annuler une installation multiple | Indisponibilité explicite ; annulation sans installation ni changement de shell |

### Intégrations après installation

| ID | Essai | Résultat attendu |
| --- | --- | --- |
| I01 | Installer fzf et zoxide avec l’option de configuration cochée | APT vérifié, puis aperçu séparé des fichiers du shell choisi ; annuler conserve les paquets sans modifier les fichiers |
| I02 | Confirmer, puis ouvrir un nouveau Bash, Zsh et Fish selon les outils disponibles | Raccourcis fzf et commandes z/zi fonctionnels ; pas de doublon lors d’une nouvelle activation |
| I03 | Tester fzf antérieur à 0.48 et une version récente | Scripts du paquet pour l’ancien, initialisation intégrée pour le récent ; refus explicite si un script manque |
| I04 | Activer les extensions Zsh puis ajouter fzf et zoxide | Complétions fonctionnelles ; suggestions et coloration chargées après les autres widgets gérés |
| I05 | Configurer bat, fd et delta | Alias fonctionnels seulement si les noms sont libres ; Git utilise delta si GIT_PAGER était absent ; configurations Git conservées |
| I06 | Activer Atuin avec fzf et direnv | Nouvel historique local, Ctrl+R Atuin, pas de synchronisation ni import ; projet direnv non autorisé automatiquement |
| I07 | Retirer une intégration puis restaurer une sauvegarde | Autres blocs et alias personnels conservés ; nouvelle session nécessaire ; restauration conforme à l’aperçu |
| I08 | Préparer une configuration manuelle, un bloc invalide, un lien symbolique ou une modification pendant l’aperçu | Refus sans écrasement ; paquets déjà installés clairement distingués de la configuration non appliquée |

Les tests automatisés vérifient le contenu généré et les écritures. Seuls ces
essais de nouveaux terminaux peuvent confirmer le chargement réel des hooks.

### Réglages, alias et transfert personnels

| ID | Essai | Résultat attendu |
| --- | --- | --- |
| P01 | Rechercher fd-find, puis filtrer les outils installés, disponibles et compatibles avec Fish/Zsh | Résultats pertinents et catégories vides masquées ; sélections conservées même lorsqu’elles sont masquées |
| P02 | Consulter les états avec bloc géré, initialisation manuelle, fichier absent et fichier modifié | États distincts ; aucune affirmation qu’un terminal existant a chargé la configuration |
| P03 | Modifier chaque option Starship/fzf/bat puis ouvrir le shell concerné | Réglages visibles ; aperçu fzf fonctionnel ; complétions et autres réglages conservés |
| P04 | Modifier les options eza/tmux puis utiliser mtk-eza et mtk-tmux | Options appliquées ; serveur tmux distinct, configurations habituelles conservées |
| P05 | Ajouter, modifier puis retirer un alias dans Bash, Zsh et Fish | Raccourci chargé dans un nouveau shell, arguments conservés, autres alias inchangés ; aucune exécution lors de l’enregistrement |
| P06 | Proposer un nom réservé, un alias manuel existant ou le masquage d’une commande | Refus pour les deux premiers ; masquage explicitement annoncé avant confirmation |
| P07 | Exporter, consulter le JSON puis importer dans un autre compte/VM avec d’autres chemins | Aperçu complet, fichier privé, paquets manquants proposés, chemins et hooks régénérés, alias et réglages retrouvés |
| P08 | Importer un JSON invalide, un outil inconnu, une police absente ou modifier un fichier pendant la confirmation | Refus explicite ; fichiers locaux conservés ; paquets déjà installés distingués de la configuration |
| P09 | Annuler chaque aperçu, occuper la réservation depuis un autre module puis utiliser --dry-run | Aucun fichier modifié à l’annulation ou en simulation ; opération concurrente refusée |

Valider notamment le passage d’Alacritty YAML à TOML entre deux machines et la
reprise des choix Kitty. Les alias contenant des chemins personnels nécessitent
une vérification par l’utilisateur ; leurs commandes ne sont pas réécrites.
