# Exporter un rapport de diagnostic

Depuis **Accueil**, la carte **Rapport de diagnostic** permet de préparer un
fichier Markdown pour le dépannage. Rien n’est envoyé automatiquement : le
partage du fichier reste manuel.

## Parcours

1. Choisir si les 20 dernières opérations doivent être incluses.
2. Cliquer sur **Prévisualiser le rapport de diagnostic…**. Une nouvelle collecte
   est effectuée ; les anciennes valeurs affichées à l’accueil ne sont pas réutilisées.
3. Lire l’intégralité du texte dans l’aperçu. Annuler n’écrit aucun rapport.
4. Choisir **Enregistrer le rapport…**, puis un nouveau nom de fichier.
5. Partager le fichier seulement après vérification de son contenu.

Le texte enregistré correspond exactement à l’aperçu accepté. Le rapport n’est
pas recalculé au moment de l’enregistrement. Un fichier ou un lien déjà présent
à la destination est conservé ; choisir un autre nom pour exporter à nouveau.
Les nouveaux fichiers utilisent les permissions privées `0600`.

## Contenu

- Date de collecte en UTC et version de MintTweaks.
- Versions de Python, du système, du noyau et du paquet Cinnamon.
- Architecture, type de session X11/Wayland, durée de fonctionnement,
  mémoire et espace disque lorsque ces mesures sont disponibles.
- Résultats des diagnostics de l’accueil : base de paquets, dépendances,
  services en échec, erreurs de démarrage, disque, redémarrage et anciens noyaux.
- Si demandé, au plus 20 opérations récentes avec date UTC, identifiant de
  module, résultat et indication réel/simulation.

Un contrôle indisponible est signalé comme tel. Il ne devient pas un contrôle
réussi. Une erreur de lecture de l’historique n’empêche pas d’exporter les autres
observations ; sa présence est signalée dans le rapport.

Les diagnostics sont des observations successives, sans transaction commune
avec les autres outils du système. Ils peuvent évoluer pendant la collecte.

## Informations exclues et masquage

Le rapport ne recopie pas le nom de la machine, le nom du compte, les noms des
opérations, les chemins des sauvegardes, les configurations ou les journaux
techniques de MintTweaks. Les extraits de commandes et de journal système ainsi
que les noms des services en échec sont remplacés par une mention d’omission.
Cette exclusion précède le formatage du rapport.

Un filtrage complémentaire masque les identifiants locaux connus, chemins,
adresses IP, adresses MAC, courriels, URL et affectations courantes de secrets
qui apparaîtraient dans les champs conservés. Les valeurs insérées sont échappées
pour ne pas créer de liens, d’images ou de HTML dans un lecteur Markdown.
L’aperçu permet de vérifier le résultat avant de le partager.

## Fonctionnement et validation

La collecte utilise les diagnostics en lecture seule existants, puis deux lectures
supplémentaires : architecture Debian et version du paquet Cinnamon. Elle n’exige
ni droits administrateur ni accès réseau. Le bouton est désactivé en simulation ;
l’API d’enregistrement respecte également ce mode sans écrire de rapport.

L’enregistrement utilise la réservation commune des opérations. Il écrit un
fichier temporaire privé, puis publie le contenu complet sans remplacer une
destination existante. Une erreur d’écriture avant publication ne laisse pas de
rapport partiel. L’export apparaît dans l’historique ; le nom du fichier exporté
n’est pas ajouté à ses métadonnées.

Les tests automatisés couvrent les exclusions, le masquage, les contrôles
indisponibles, les erreurs d’historique, l’aperçu, les annulations, les écritures
privées et la conservation des fichiers existants. Le rendu de l’aperçu et la
boîte de sélection restent à vérifier dans une session Linux Mint.
