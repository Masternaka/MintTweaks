# Vérification des nouveautés sous Mint

**État : à exécuter.** Cette liste cible les ajouts récents. Les essais déjà
réalisés par l’utilisateur ne prouvent pas le fonctionnement de ce nouveau candidat.

Utiliser une VM Cinnamon de test et transférer les sources locales complètes,
y compris les nouveaux fichiers, selon la [recette](linux-mint.md). Construire
et installer le `.deb` de ce candidat. Noter version de Mint, architecture,
version du paquet et somme SHA-256 dans le [compte rendu](compte-rendu.md).

| À faire | Essai | Résultat attendu |
| --- | --- | --- |
| ☐ | Ouvrir les douze pages, puis les aperçus et sélecteurs en français avec une petite fenêtre et au clavier | Textes lisibles, confirmations accessibles, retour possible après annulation |
| ☐ | Préparer un diagnostic avec et sans historique ; annuler puis exporter | Seul le texte approuvé est enregistré ; noms de machine/compte, chemins de sauvegarde et journaux bruts exclus |
| ☐ | Exporter/importer un profil Cinnamon deux fois, puis appliquer et restaurer explicitement | Deux nouvelles identités locales, aucun réglage appliqué à l’import ; sauvegarde associée à l’application et restauration disponible dans Cinnamon |
| ☐ | Transférer une sélection Applications vers un autre compte ou une autre VM | Choix installés, indisponibles et polices GitHub distingués ; seuls les choix APT installables sont cochés ; installation soumise à un autre aperçu |
| ☐ | Importer une référence Dotfiles et choisir les dossiers locaux ; cloner, analyser, activer puis restaurer explicitement | Aucun clonage ni lien à l’import ; conflits signalés avant activation, fichiers sauvegardés et restauration vérifiée |
| ☐ | Transférer les choix Terminal entre comptes, ouvrir de nouveaux shells, puis restaurer | Réglages et alias retrouvés, chemins régénérés ; alias personnels relus ; sauvegardes accessibles depuis le module |
| ☐ | Annuler chaque aperçu et sélecteur ; essayer un nom d’export existant, un lien et un JSON invalide ; modifier un fichier local après aperçu | Aucun écrasement ; refus clair ; contrôles utilisables après l’erreur. Une annulation après installation de paquets Terminal conserve ces paquets |
| ☐ | Démarrer une opération, tenter une modification depuis une autre page, puis consulter Historique | Seconde opération refusée ; première suivie jusqu’à sa fin ; résultat et références de sauvegarde cohérents, sans contenu privé |
| ☐ | Consulter les observations d’une étape de l’assistant, changer d’étape pendant l’analyse et rouvrir le parcours | Résultat périmé ignoré ; notes et progression déclarée conservées ; observation distincte de la validation manuelle |
| ☐ | Installer puis lancer Helium, Brave et Zen ; inspecter leurs détails | Sources APT attendues pour Helium/Brave ; Zen installé pour le compte courant depuis son script officiel approuvé ; ancien paquet Debian Zen signalé sans remplacement implicite |
| ☐ | Relancer avec `--dry-run`, puis essayer les mêmes actions | Fenêtre de simulation distincte ; aucune modification des paquets, réglages, profils, liens ou fichiers exportés ; historique de simulation séparé |

Les étapes détaillées figurent dans la [recette complète](linux-mint.md),
notamment C01–C06, SA01–SA06 et RF01–RF06. Un export contient les choix propres
à son module ; il ne constitue pas une sauvegarde du système.

Consigner chaque ligne comme réussie, échouée, bloquée ou non effectuée, avec une
preuve. Les tests Python et les doubles GTK exécutés sur macOS vérifient la
logique ; ils ne valident ni le rendu graphique, ni polkit, ni APT, ni le chargement
réel des réglages sous Mint. Avant publication, terminer aussi la recette globale
du paquet, des nettoyages et des restaurations.
