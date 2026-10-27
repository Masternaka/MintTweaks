# Administration du système

## Accueil

- Résumé en lecture seule de la machine : distribution, noyau, nom d’hôte, temps de fonctionnement, mémoire et occupation du disque racine.
- Diagnostics automatiques : paquets à moitié configurés, dépendances cassées, services systemd en échec, erreurs journalisées depuis le démarrage, espace disque, redémarrage requis et anciens noyaux.
- Les contrôles indisponibles sont comptés séparément des réussites : un outil absent, un délai dépassé, une lecture refusée ou une simulation ne produit pas de diagnostic positif. L’échec d’un contrôle laisse les autres résultats accessibles.
- Accès direct aux autres modules depuis la page d’accueil.

## Entretien

- Tailles réelles du cache APT, du journal système, des miniatures et de la corbeille.
- **Aperçu de `apt-get autoremove` avant toute suppression** : les deux accès à cette action présentent la liste complète dans une fenêtre défilante. Une nouvelle simulation est vérifiée après confirmation ; un échec ou une liste différente bloque la suppression.
- Nettoyage en un clic : paquets orphelins, fichiers `.deb` obsolètes, dépendances cassées, réduction du journal par taille ou ancienneté, cache des miniatures, corbeille et environnements d’exécution Flatpak inutilisés.
- Gestion prudente des noyaux : le noyau en cours d’utilisation et le plus récent ne sont jamais proposés à la suppression. Tous les paquets associés à un noyau sélectionné sont supprimés en un seul `apt-get purge`.

## Services

- Tableau filtrable de toutes les unités `*.service`, avec leur état d’exécution et leur activation au démarrage.
- Démarrage, arrêt, redémarrage, activation et désactivation, avec confirmation des actions susceptibles d’interrompre un service.
- Consultation du journal de chaque unité et option *Lire en tant qu’administrateur* lorsque le journal accessible sans privilèges est vide.
- Analyse du démarrage : résumé de `systemd-analyze`, unités les plus lentes et chaîne critique.
- En cas d’échec de lecture, les derniers services restent affichés avec une mention indiquant qu’ils n’ont pas été actualisés ; les actions sont désactivées jusqu’à une lecture réussie. Les résultats partiels des journaux et de l’analyse du démarrage signalent leurs limites.

## Samba

- Installation de `samba`, `smbclient` et `cifs-utils` depuis l’application.
- Gestion complète des partages : création, modification, renommage et suppression, sélection de dossier, visibilité, lecture seule, accès invité, `valid users`, `write list`, masques et `force group`.
- Gestion des comptes Samba : création, changement de mot de passe, activation, désactivation et suppression. Les mots de passe passent par l’**entrée standard** de `smbpasswd`, jamais par la ligne de commande.
- Éditeur de `smb.conf` avec **validation par `testparm`**, nettoyage des doublons et sélection d’une sauvegarde à restaurer.
- Outils de service et de pare-feu : activation et démarrage de `smbd`/`nmbd`, rechargement de la configuration, autorisation de Samba dans `ufw` et liste des connexions actives.

L’interface est **traduite en français** et suit la langue du système ; `--lang fr` permet de la forcer. Voir les [instructions de traduction](../developpement/architecture.md#langues).

## Firefox

- Catalogue de 16 extensions courantes (uBlock Origin, Privacy Badger, ClearURLs, Bitwarden, Dark Reader, SponsorBlock, etc.) avec une case à cocher par extension.
- Détection en lecture seule des extensions déjà installées dans le profil Firefox natif.
- Installation des extensions cochées via la politique d’entreprise `ExtensionSettings` : Firefox les télécharge lui-même depuis `addons.mozilla.org` à son prochain démarrage, ce qui garantit la vérification des signatures.
- Fusion prudente de `/etc/firefox/policies/policies.json` : les autres politiques et les extensions gérées par un administrateur sont conservées ; une entrée existante avec un autre mode ou une autre URL est refusée plutôt que remplacée.
- Sauvegarde root de la politique précédente dans `/var/backups/minttweaks/` avant chaque écriture.

La politique s’applique au Firefox natif fourni par Linux Mint.

