# Logiciels natifs hors dépôts officiels de Mint

Le module installe uniquement les applications de son catalogue limité, depuis
des sources APT tierces explicitement identifiées. Il ne remplace pas le
gestionnaire de logiciels Mint. Les applications des dépôts officiels de Mint,
les installations Flatpak et les téléchargements libres saisis par l’utilisateur
ne font pas partie de ce module.

## Premier catalogue

| Application | Paquet | Source attendue | Architectures de cette source |
| --- | --- | --- | --- |
| Helium Browser | `helium-bin` | [Dépôt officiel Helium](https://github.com/imputnet/helium-linux#debianubuntu), `https://pkg.helium.computer/deb/`, suite `stable/main` | amd64, arm64 |
| Brave Browser | `brave-browser` | [Dépôt officiel Brave](https://brave.com/linux/), `https://brave-browser-apt-release.s3.brave.com/`, suite `stable/main` | amd64, arm64 |
| Zen Browser | `zen-browser` | [Dépôt Masternaka](https://github.com/Masternaka/masternaka-repository#installation-sur-linux-mint), `https://masternaka.github.io/masternaka-repository/`, suite plate `./` | amd64 |

La voie Zen proposée est un **paquet Debian non officiel**, construit par le dépôt
Masternaka à partir de l’archive amont. Les [instructions officielles Zen](https://docs.zen-browser.app/guides/install-linux)
proposent notamment une archive native ; elles ne décrivent pas ce paquet comme
un `.deb` officiel. Le module distingue ces provenances dans la page et l’aperçu.

La disponibilité réelle du dépôt central n’est pas établie par ce catalogue.
Sa publication, sa signature, son activation et sa validation Linux relèvent du
projet de dépôt. Il n’est pas modifié ni activé par MintTweaks.

## Préparer la source

Chaque dépôt doit être configuré séparément selon son guide, avec sa clé de
signature, puis les métadonnées APT doivent être actualisées avec les outils de
Mint. Les liens **Instructions de configuration du dépôt** ouvrent ces guides.
Ils ne modifient pas la configuration automatiquement.

MintTweaks n’ajoute ni fichier de source, ni clé, ni script d’installation. Une
architecture non prise en charge, un candidat absent, une suite de préversion ou
une source différente empêche l’installation. Si une même version candidate est
proposée par plusieurs sources distinctes, le module refuse de choisir à la
place de l’utilisateur et demande de clarifier la configuration APT.

La vérification repose sur les métadonnées APT configurées. Les téléchargements
et les contrôles de confiance restent gérés par APT ; aucun contournement des
signatures ou des contrôles APT n’est ajouté.

## Parcours d’installation

1. Ouvrir **Logiciels natifs**, puis **Réanalyser**.
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

Les tests automatisés utilisent un exécuteur APT simulé. Ils couvrent les
origines, suites et architectures, les aperçus, les changements de plan, les
refus de suppression, les erreurs polkit/APT et la vérification finale des
versions. Aucune installation réelle n’a été effectuée sur ce Mac.

La [recette Mint](../validation/linux-mint.md) doit vérifier les sources configurées,
une installation de chaque navigateur, son lancement, un refus polkit, un échec
réseau, un plan modifié, une installation partielle et la migration d’un ancien
parcours. La présence d’un candidat APT ne prouve pas que son navigateur démarre
correctement sous la version de Mint testée.
