# Assistant après installation

L’assistant est un parcours guidé facultatif vers les modules disponibles. Il
conserve une sélection d’étapes et leur progression déclarée par l’utilisateur.
Il ne lance pas de série automatique d’installations ou de modifications.

## Vérification du support d’installation Live

Une section dédiée explique le rôle de `casper-md5check.service` : vérifier les
fichiers de la clé USB ou du DVD d’installation. Sur une installation sur disque,
ce contrôle est inutile et peut échouer lorsque le fichier de sommes MD5 du
support est absent. Cela ne signifie pas que des fichiers corrompus ont été détectés.

**Désactiver la vérification du support Live** arrête et désactive uniquement ce
service, puis efface son état d’échec. L’action demande confirmation et une
autorisation administrateur. Elle ne modifie pas les vérifications du système de
fichiers du disque et reste indépendante de la progression du parcours.

Le bouton est indisponible en session Live, en simulation, si le service est
absent ou déjà désactivé et inactif, ou si les diagnostics ne permettent pas de
confirmer une installation sur disque et l’état du service. Ces conditions sont
revérifiées avant la modification. **Recharger l’état du service** permet de
réessayer la lecture après une erreur. Le service reste visible dans **Services** ;
cette option ne masque aucun échec.

## Étapes disponibles

| Étape | Module ouvert | Objectif et changements possibles |
| --- | --- | --- |
| Vérifier le système | Accueil | Lire les diagnostics ; aucune modification lors de cette consultation |
| Installer des logiciels natifs tiers | Logiciels natifs | Helium et Brave par APT officiel avec aperçu ; Zen par son installateur GitHub officiel sans droits administrateur |
| Préparer les shells et terminaux | Shells et terminaux | Installer les outils, choisir le shell de connexion et personnaliser Kitty ou Alacritty après aperçu et sauvegarde |
| Préparer Firefox | Firefox | Choisir les extensions d’addons.mozilla.org ; écriture de la politique avec privilèges administrateur, puis redémarrage du navigateur |
| Choisir l’apparence | Profils Cinnamon | Enregistrer ou appliquer des réglages utilisateur après aperçu et sauvegarde ; les thèmes et polices doivent déjà être installés |
| Configurer le partage si nécessaire | Samba | Gérer les partages et comptes ; les installations, services et règles de pare-feu restent pilotés depuis Samba |

Voir le [guide Shells et terminaux](shells-et-terminaux.md) pour les détails.

## Observations facultatives

Après avoir enregistré la sélection et choisi une étape, utiliser **Observer
l’étape sélectionnée** pour consulter des observations locales en lecture seule.
Le résultat est séparé de **Vérifié par vous** : il ne modifie ni la progression,
ni une note saisie ou enregistrée, et ne valide aucune étape automatiquement.

| Étape | Ce qui est observé | Confirmation qui reste manuelle |
| --- | --- | --- |
| Système | Résultats des diagnostics actuels de l’accueil | Anomalies à examiner dans leur contexte |
| Logiciels natifs | Versions des paquets ou fichiers utilisateur reconnus ; ancien paquet Zen signalé | Choix des navigateurs, provenance, lancement et mises à jour |
| Terminal | Shell de connexion, préférences enregistrées et paquets Bash/Zsh/Fish/Kitty/Alacritty | Chargement des intégrations dans une nouvelle session et outils effectivement souhaités |
| Firefox | Exécutable natif dans PATH et extensions du catalogue configurées dans la politique système | Installation, activation et chargement effectifs des extensions dans Firefox |
| Cinnamon | Lecture des réglages et présence de profils enregistrés | Profil réellement voulu et résultat visuel |
| Samba | Paquet Samba, état de smbd et définitions de partages lisibles | Validité avec testparm, comptes, pare-feu, permissions et accès depuis un client |

Les mentions **Détecté**, **Non détecté**, **À examiner manuellement** et
**Indisponible** décrivent uniquement les lectures effectuées. Une lecture
refusée ne devient pas une absence ou une réussite. Des outils ou navigateurs
non détectés peuvent être facultatifs ou installés dans un autre format.

Les observations n’installent rien, ne lancent aucun navigateur, ne chargent
aucun script de shell et ne demandent pas de droits administrateur. Elles ne
consultent pas les comptes Samba ni les règles de pare-feu qui exigeraient ces
droits. Les sorties brutes, noms de partages, chemins et contenus des
configurations ne sont pas recopiés dans le résultat ; seul le shell de connexion
est présenté par son chemin système.

Le contrôle est déclenché manuellement et horodaté dans le fuseau local. Ses
résultats restent en mémoire, sans nouveau format du fichier de progression.
Changer de sélection, recharger la progression ou lancer une opération dans
MintTweaks les efface. Un résultat reçu après ces changements est écarté ;
répéter l’observation si nécessaire. Les autres applications peuvent modifier
le système sans notification : l’observation reste un instantané.

Le bouton est désactivé en simulation, si la sélection n’est pas enregistrée ou
si une modification est en cours. Une observation indisponible n’empêche pas
de déclarer ensuite son propre résultat.

## Utilisation

1. Ouvrir **Après installation** depuis l’accueil ou la barre latérale.
2. Cocher seulement les étapes souhaitées et consulter leur récapitulatif.
3. Choisir **Enregistrer les étapes sélectionnées**. Une sélection vide est
   autorisée et n’efface pas la progression des étapes précédemment choisies.
4. Choisir **Ouvrir la prochaine étape inachevée**, puis effectuer les actions
   souhaitées dans le module. Ses contrôles et confirmations restent applicables.
5. Revenir dans l’assistant, choisir l’étape dans la liste, saisir au besoin une
   note et enregistrer son état : **vérifié par vous**, **à reprendre** ou **à faire**.
6. Après réouverture, reprendre à la première étape sélectionnée qui n’est pas
   marquée comme vérifiée.

Ouvrir une page ne modifie jamais son état de progression. Une étape vérifiée est
une déclaration de l’utilisateur après contrôle, pas une validation automatique
du système. Une note est enregistrée avec le bouton d’état ; elle n’est pas
sauvegardée automatiquement pendant la saisie.

Les étapes vérifiées ne sont pas rejouées automatiquement. Elles restent
consultables avec **Ouvrir l’étape sélectionnée**. **Marquer à faire** permet de
les réintroduire dans le parcours. Décocher puis recocher une étape conserve son
état et sa note ; cela permet de modifier le parcours sans perdre l’historique
du résultat déclaré pour cette étape.

Une sélection modifiée doit être enregistrée avant de reprendre le parcours ou
de noter un résultat. Le rechargement demande confirmation avant d’abandonner
une sélection non enregistrée.

## Persistance et limites

La progression est stockée dans `$XDG_DATA_HOME/minttweaks/setup-plan.json`, ou
par défaut `~/.local/share/minttweaks/setup-plan.json`. Le fichier privé est écrit
en `0600`, via un fichier temporaire et un remplacement atomique. Il contient un
numéro de format (`schema_version: 3`), un identifiant de révision, une date avec
fuseau horaire, la sélection et l’état ainsi qu’une note de 500 caractères au
maximum pour chacune des six étapes connues. Les anciens fichiers de formats 1 et 2
sont lus sans être réécrits : les anciennes sélections, notes et vérifications
sont conservées et les nouvelles étapes absentes de l’ancien format restent non sélectionnées (Logiciels natifs pour le format 1 et Shells et terminaux pour les formats 1 et 2).
La migration est enregistrée lors de la prochaine sauvegarde explicite.

Une révision modifiée depuis la dernière lecture provoque un refus de sauvegarde
et demande un rechargement. Ce contrôle ne constitue pas un verrou global contre
un programme extérieur qui modifierait le fichier au même moment. Les fichiers
invalides, trop volumineux, symboliques ou de version inconnue sont signalés et
laissés en place ; l’assistant ne les réinitialise pas silencieusement.

Les écritures de progression utilisent la réservation commune de MintTweaks et
n’exécutent aucune commande système. Elles sont désactivées en simulation. Le
guide propose des observations partielles uniquement sur demande ; elles ne
valident pas les résultats des autres modules. Il ne conserve ni leurs mots de
passe ni leurs sorties de commandes. La suppression
automatique des anciennes notes, l’export et l’exécution groupée ne sont pas
proposés.

## Validation

Les tests automatisés couvrent la sélection, la réouverture, la reprise après un
résultat à reprendre, la conservation des étapes vérifiées, les révisions
périmées, les erreurs d’écriture, les fichiers invalides et la navigation sans
validation implicite. Les états GTK sont vérifiés avec les doublures existantes.
Les tests du contrôle Live couvrent le refus en session Live, les diagnostics
indisponibles, la simulation, le périmètre des commandes administrateur et les
erreurs d’autorisation. Sur la machine de test, vérifier aussi l’explication
visible, la confirmation et le rechargement dans **Services** après désactivation.

Les nouveaux contrôles facultatifs restent à vérifier sous Mint. Les essais
détaillés du parcours restent à consigner : sélection et récapitulatif,
navigation vers chaque module, déclaration d’un résultat avec une note,
réouverture et reprise sans rejouer une étape, simulation et affichage sur une
petite fenêtre. Utiliser la [recette Mint](../validation/linux-mint.md) pour consigner
ces essais séparément des tests automatisés.
