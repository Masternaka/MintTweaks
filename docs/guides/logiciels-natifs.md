# Logiciels natifs hors dépôts officiels de Mint

Le module installe uniquement les applications de son catalogue limité, depuis
leurs sources officielles explicitement identifiées. Helium et Brave utilisent
APT ; Zen utilise son installateur GitHub officiel pour le compte courant. Il ne remplace pas le
gestionnaire de logiciels Mint. Les applications des dépôts officiels de Mint,
les installations Flatpak et les téléchargements libres saisis par l’utilisateur
ne font pas partie de ce module.

## Premier catalogue

| Application | Paquet | Source attendue | Architectures de cette source |
| --- | --- | --- | --- |
| Helium Browser | `helium-bin` | [Dépôt officiel Helium](https://github.com/imputnet/helium-linux#debianubuntu), `https://pkg.helium.computer/deb/`, suite `stable/main` | amd64, arm64 |
| Brave Browser | `brave-browser` | [Dépôt officiel Brave](https://brave.com/linux/), `https://brave-browser-apt-release.s3.brave.com/`, suite `stable/main` | amd64, arm64 |
| Zen Browser | Archive native utilisateur | [Installateur officiel Zen](https://docs.zen-browser.app/guides/install-linux), depuis GitHub `zen-browser/updates-server` et `zen-browser/desktop` | amd64, arm64 |

Helium et Zen ne passent plus par le dépôt Masternaka. Ce dernier reste
disponible pour MintTweaks et les projets personnels de Masternaka.

La publication du dépôt central reste gérée par son projet séparé. MintTweaks
peut désormais ajouter sa source sur la machine cliente ; cela ne modifie pas
le dépôt GitHub, ses secrets ou sa publication.

## Préparer la source

### Helium et Brave

Pour Helium et Brave, **Configurer le dépôt et installer…** affiche la provenance,
l’URL du dépôt et celle de sa clé. Après confirmation et autorisation
administrateur, MintTweaks télécharge la clé par HTTPS, vérifie son format avec
GPG et ajoute une source limitée à cette clé par `signed-by`. Aucun script distant
n’est exécuté. Les recettes suivent les guides officiels liés dans le catalogue.

Les nouveaux fichiers sont nommés `minttweaks-helium.gpg` ou
`minttweaks-brave.gpg` dans `/usr/share/keyrings`, et `minttweaks-<application>.list`
dans `/etc/apt/sources.list.d`. Les fichiers existants ne sont pas remplacés.
Si une source mentionne déjà le dépôt, seule l’actualisation APT est effectuée ;
un conflit dans cette configuration reste à corriger avec les outils de Mint.

L’actualisation APT est suivie d’une nouvelle vérification du candidat, puis de
l’aperçu d’installation. Annuler l’installation conserve le dépôt configuré pour
les futures installations et mises à jour. Si l’ajout ou l’actualisation échoue,
les fichiers nouvellement créés par cette opération sont retirés ; les sources
préexistantes sont conservées.

Les liens **Instructions d’installation** restent disponibles pour
une configuration manuelle. Une architecture non prise en charge, un candidat
absent, une suite de préversion ou une source différente empêche l’installation.
Si une même version candidate est proposée par plusieurs sources distinctes, le
module demande de clarifier la configuration APT.

### Zen depuis GitHub

Le bouton **Installer Zen depuis GitHub…** télécharge le script documenté par
Zen, puis présente son URL, son SHA-256 et les trois destinations :

- `~/.tarball-installations/zen` ;
- `~/.local/bin/zen` ;
- `~/.local/share/applications/zen.desktop`.

Après confirmation, MintTweaks exécute exactement le script téléchargé, avec
Bash et sans élévation de privilèges. Ce script télécharge l’archive courante de
`zen-browser/desktop` et crée le lanceur et l’entrée du menu. Le SHA-256 affiché
identifie les octets du script à exécuter ; il ne constitue pas une signature
amont et ne fixe pas la version de l’archive choisie pendant son exécution.
Les mises à jour suivantes passent par Zen. Le module vérifie la présence de
l’exécutable, du lanceur, de l’entrée de menu et de la version dans
`application.ini`, sans lancer le navigateur.

Une installation utilisateur reconnue est affichée comme déjà installée. Des
fichiers existants incomplets, même des liens cassés, bloquent l’opération pour
éviter leur remplacement. Un échec peut laisser des fichiers créés par le script
amont : les vérifier avant de réessayer. Le mode simulation ne télécharge rien,
n’écrit rien et n’exécute pas le script.

Si l’ancien paquet Debian `zen-browser` est installé, MintTweaks demande sa
suppression avec le gestionnaire de paquets de Mint avant de proposer la voie
officielle. Conserver les profils et sauvegarder ses données avant la transition ;
MintTweaks ne supprime ni ne migre automatiquement de profil. Une installation
Flatpak ou une copie placée ailleurs n’est pas détectée par cette vérification.

### Masternaka

Dans **Logiciels natifs**, le bouton **Configurer ou actualiser le dépôt
Masternaka** affiche une confirmation avec l’URL, l’empreinte et les fichiers
concernés. Après autorisation polkit, il ajoute uniquement :

- `/etc/apt/keyrings/masternaka.asc` : la clé publique fournie avec MintTweaks ;
- `/etc/apt/sources.list.d/masternaka.list` : la source HTTPS plate, avec `signed-by`.

Empreinte : `86A7954635E2B4A77CAC8F00E25B26CC99FBDB1C`. Les octets de la clé
publique incluse sont contrôlés par SHA-256 avant toute écriture. Aucune clé
privée ni phrase secrète n’est requise ou distribuée. La clé n’est pas ajoutée
aux trousseaux de confiance globaux d’APT. Une rotation de clé nécessite une
mise à jour du fichier public inclus et de son empreinte et SHA-256 épinglés.

Le helper dédié n’accepte qu’une action fixe, sans chemin ou URL fournis par
l’utilisateur. Il refuse les liens symboliques, les chemins système modifiables
par un utilisateur et les fichiers existants différents. Il préserve les fichiers
déjà conformes et peut compléter une configuration partielle. Les nouveaux
fichiers sont publiés sans écrasement ; aucune configuration personnalisée
existante n’est remplacée. Un verrou évite deux ajouts simultanés par ce helper.

L’action actualise uniquement les métadonnées de cette source avec APT, en
conservant les vérifications de signature. Si l’actualisation échoue, les fichiers
créés pendant cette tentative sont retirés ; les fichiers préexistants restent
en place. Les métadonnées APT éventuellement téléchargées ne sont pas effacées.
Un échec laisse un message explicite dans le journal. Aucun paquet n’est installé
ou mis à niveau ; les mises à jour suivantes passent par les outils APT/Mint
selon leur configuration. Le mode simulation ne change aucun fichier et ne
contacte pas le réseau.

Les sources officielles Helium et Brave conservent leurs boutons dédiés décrits ci-dessus. Les liens
**Instructions d’installation** ouvrent ces guides sans les exécuter.
Le catalogue Helium continue de viser sa source officielle, et Brave la sienne ;
l’ajout de Masternaka ne remplace pas ces choix par une autre provenance. Une
architecture non prise en charge, un candidat absent, une suite de préversion ou
une source différente empêche l’installation. Si une même version candidate est
proposée par plusieurs sources distinctes, le module refuse de choisir à la
place de l’utilisateur et demande de clarifier la configuration APT.

La vérification repose sur les métadonnées APT configurées. Les téléchargements
et les contrôles de confiance restent gérés par APT ; aucun contournement des
signatures ou des contrôles APT n’est ajouté.

## Parcours d’installation

1. Ouvrir **Logiciels natifs**. Pour Zen, utiliser **Installer Zen depuis GitHub…** et suivre la confirmation dédiée. Pour Helium et Brave, utiliser **Configurer le dépôt et installer…** si la source manque, puis confirmer. Les étapes APT ci-dessous concernent Helium et Brave. Utiliser **Réanalyser** pour actualiser les états.
2. Contrôler la source, l’état du paquet et sa version candidate. La détection
   porte sur le paquet Debian nommé dans le catalogue, pas sur toutes les copies
   du navigateur éventuellement installées manuellement ou dans un autre format.
3. Cocher les paquets disponibles et non installés. Les paquets déjà installés
   ne sont ni réinstallés ni mis à jour par cette action.
4. Choisir **Prévisualiser les installations sélectionnées**. L’aperçu présente
   les applications, sources et versions, puis toute la sortie de simulation APT,
   avec les dépendances et éventuelles mises à niveau nécessaires.
5. Confirmer après lecture. Une nouvelle simulation doit correspondre au plan
   confirmé avant l’exécution avec autorisation administrateur.
6. Vérifier le résultat et les versions relues après installation. Les mises à
   jour ultérieures restent pilotées par les outils APT et Mint selon leur
   configuration, depuis les sources configurées.

Les versions des paquets demandés sont fixées dans la commande `apt-get install`.
L’option `--no-remove` interdit les suppressions proposées par la résolution des
dépendances ; toute suppression dans l’aperçu est également refusée en amont.
Les dépendances peuvent être installées ou mises à niveau. La simulation n’est
pas une transaction verrouillée avec l’exécution : éviter les opérations de
paquets concurrentes depuis d’autres outils pendant l’installation.

Les modifications utilisent la réservation commune de l’application. La
simulation MintTweaks n’installe rien ; faute de lectures réelles en simulation,
la page ne prétend pas connaître la disponibilité du catalogue.

Un échec APT ou une version finale non vérifiée reste une erreur, même si une
partie de l’installation a réussi. Aucune désinstallation automatique n’est
tentée : les paquets effectivement installés sont détectés à l’actualisation,
et l’utilisateur peut reprendre les autres après vérification de l’état APT.

## Assistant et données existantes

L’assistant après installation propose désormais une étape Logiciels natifs.
La progression reste déclarée par l’utilisateur ; une installation ne valide
pas automatiquement cette étape.

La progression utilise le format courant de l’assistant, qui lit aussi les anciens
formats sans réécrire le fichier à l’ouverture. Les sélections, notes et états
existants sont conservés ; les nouvelles étapes restent non sélectionnées. Voir
le [guide de l’assistant](assistant-apres-installation.md#persistance-et-limites).

## Validation restante

Les tests automatisés utilisent des exécuteurs simulés et des fichiers temporaires.
Ils couvrent les origines APT, suites et architectures, les aperçus, les changements
de plan, les refus de suppression et les erreurs polkit/APT. Pour Zen, ils vérifient
la source GitHub fixe, l’annulation, les conflits avec l’ancien paquet ou des
fichiers existants, le script approuvé exécuté sans droits administrateur, les
échecs réseau et la vérification finale. Aucun script amont ni navigateur réel
n’est exécuté par ces tests.

La [recette Mint](../validation/linux-mint.md) doit vérifier les installations
réelles, le lancement, les mises à jour, le sandbox et la transition depuis
l’ancien paquet Zen. Ces essais restent à effectuer sous Linux Mint ; les tests
sur Mac ne prouvent pas le fonctionnement graphique ni les politiques AppArmor.

## Détails d’installation

Chaque entrée présente un volet avec sa méthode, sa portée, sa source attendue,
les versions ou révisions disponibles et les indications de mise à jour et de
retrait. Voir [Comprendre les installations](installations.md) pour la distinction
entre candidat vérifié, paquet déjà installé et copie utilisateur.
