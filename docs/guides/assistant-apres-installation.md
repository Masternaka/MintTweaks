# Assistant après installation

L’assistant est un parcours guidé facultatif vers les modules disponibles. Il
conserve une sélection d’étapes et leur progression déclarée par l’utilisateur.
Il ne lance pas de série automatique d’installations ou de modifications.

## Étapes disponibles

| Étape | Module ouvert | Objectif et changements possibles |
| --- | --- | --- |
| Vérifier le système | Accueil | Lire les diagnostics ; aucune modification lors de cette consultation |
| Installer des logiciels natifs tiers | Logiciels natifs | Choisir Helium, Brave ou Zen depuis leurs sources attendues ; aperçu APT et autorisation administrateur avant installation |
| Préparer les shells et terminaux | Shells et terminaux | Installer les outils, choisir le shell de connexion et personnaliser Kitty ou Alacritty après aperçu et sauvegarde |
| Préparer Firefox | Firefox | Choisir les extensions d’addons.mozilla.org ; écriture de la politique avec privilèges administrateur, puis redémarrage du navigateur |
| Choisir l’apparence | Profils Cinnamon | Enregistrer ou appliquer des réglages utilisateur après aperçu et sauvegarde ; les thèmes et polices doivent déjà être installés |
| Configurer le partage si nécessaire | Samba | Gérer les partages et comptes ; les installations, services et règles de pare-feu restent pilotés depuis Samba |

Voir le [guide Shells et terminaux](shells-et-terminaux.md) pour les détails.

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
guide ne vérifie pas automatiquement les résultats dans les autres modules et
ne conserve ni leurs mots de passe ni leurs sorties de commandes. La suppression
automatique des anciennes notes, l’export et l’exécution groupée ne sont pas
proposés.

## Validation

Les tests automatisés couvrent la sélection, la réouverture, la reprise après un
résultat à reprendre, la conservation des étapes vérifiées, les révisions
périmées, les erreurs d’écriture, les fichiers invalides et la navigation sans
validation implicite. Les états GTK sont vérifiés avec les doublures existantes.

Les essais réels sous Mint restent à effectuer : sélection et récapitulatif,
navigation vers chaque module, déclaration d’un résultat avec une note,
réouverture et reprise sans rejouer une étape, simulation et affichage sur une
petite fenêtre. Utiliser la [recette Mint](../validation/linux-mint.md) pour consigner
ces essais séparément des tests automatisés.
