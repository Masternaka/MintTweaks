# Comprendre les installations

Dans **Applications** et **Logiciels natifs**, chaque entrée propose un volet
**Détails d’installation**. Le déplier pour consulter la méthode, la portée,
la source attendue, les versions ou révisions, les mises à jour et le retrait.
Les informations sont actualisées avec **Réanalyser** ; le volet conserve son
état ouvert ou fermé pendant cette actualisation.

## Sources et versions

La **source attendue** décrit la voie proposée par MintTweaks. Elle ne prouve
pas le dépôt utilisé pour une ancienne installation.

Pour une nouvelle installation APT disponible, MintTweaks affiche les sources
vérifiées du candidat. Dans Applications, elles comprennent origine, site,
suite et composant issus du contrôle des dépôts officiels. Pour Helium et Brave,
le candidat doit correspondre au dépôt et à la suite attendus.

Pour un paquet déjà installé, la version provient de `dpkg-query`. Son origine
de téléchargement n’est pas vérifiée par cette lecture ; le volet l’indique
explicitement. La présence d’un paquet ne prouve pas qu’il a été installé depuis
le dépôt officiel. Les vérifications de source des nouvelles installations
restent effectuées dans leurs aperçus respectifs.

La version candidate n’est pas recherchée pour les logiciels déjà présents :
le volet ne les présente donc pas comme « à jour ». Une analyse échouée est
signalée comme non vérifiée, sans être transformée en absence de logiciel.

## Méthodes et entretien

| Voie | Portée | Mises à jour | Retrait |
| --- | --- | --- | --- |
| Applications par APT | Système | Gestionnaire de mises à jour Mint ou APT, avec les sources configurées | Gestionnaire de paquets, après examen des dépendances |
| Helium et Brave par APT | Système | Même mécanisme APT, avec leurs dépôts attendus | Gestionnaire de paquets pour `helium-bin` ou `brave-browser` |
| Zen depuis GitHub | Compte courant | Outil de mise à jour intégré à Zen ; aucune recherche de nouvelle version dans ce volet | Examiner les trois emplacements affichés et retirer seulement l’application, son lanceur et son entrée de menu |
| Polices depuis GitHub | Compte courant | Pas de mise à jour automatique par APT ou MintTweaks ; examiner une nouvelle révision avant remplacement | Examiner le dossier géré de cette police, puis actualiser le cache Fontconfig |

Le volet présente des indications ; il ne lance ni mise à jour ni désinstallation.
Le retrait de logiciels peut laisser des données utilisateur. Pour Zen, conserver
`~/.zen` si les profils doivent être gardés. Les copies Flatpak ou placées ailleurs
ne sont pas analysées par la détection du catalogue.

## Alternatives APT et polices

Lorsque le module utilise `p7zip-full` à la place de `7zip`, ou `qemu-system` à
la place de `qemu`, le nom réellement détecté ou proposé apparaît dans les
détails et les indications de retrait.

Le repli GitHub des polices reste limité à l’absence confirmée du paquet APT
officiel. Une erreur APT ou une source non autorisée ne l’active pas. Le volet
présente alors les dépôts amont et le dossier géré ; la révision exacte est
choisie pendant l’aperçu GitHub, sans être inventée à partir du catalogue.

Pour une copie GitHub reconnue, la révision affichée provient du manifeste local,
après contrôle des fichiers et de leurs SHA-256. Pour Noto, les trois dépôts
amont sont affichés. Une copie installée par APT reste présentée selon sa voie
APT, même si d’autres fichiers de police existent ailleurs.

## Ancien paquet Zen

Si `zen-browser` est détecté par Debian, le volet affiche **APT**, une portée
système et sa version, avec une origine non vérifiée. Il le distingue de la
copie utilisateur proposée par l’installateur officiel. L’installation GitHub
reste bloquée tant que cet ancien paquet est présent ; le message de transition
et les recommandations de conservation du profil restent affichés.

## Validation

Les tests couvrent les sources des candidats, l’origine inconnue des paquets
installés, les alternatives, les révisions des polices, l’ancien paquet Zen et
l’actualisation des volets. Consulter les détails ne lance aucune commande
supplémentaire, aucun téléchargement et aucune opération de retrait.
Le rendu GTK et les résultats des analyses réelles restent à vérifier sous Mint.
