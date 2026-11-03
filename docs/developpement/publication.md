# Versions et publications

## Deux canaux

| Déclencheur | Version du paquet, exemple | Publication GitHub |
| --- | --- | --- |
| Push sur `main` | `0.1.4~dev.12.1.abcdef123456` | Préversion, jamais `Latest` |
| Lancement manuel sur `main` | `0.1.4~dev.13.1.abcdef123456` | Préversion, jamais `Latest` |
| Push du tag `v0.1.4` | `0.1.4` | Version standard, avec sélection automatique de `Latest` par GitHub |
| Pull request vers `main` | Aucun paquet publié | Tests et vérifications uniquement |

Une exécution manuelle sur une autre branche ou un tag est refusée. Un tag
stable doit correspondre exactement à la version des sources ; son commit doit
appartenir à l’historique de `main`. Un tag comme `v0.1.4-rc1` n’est pas accepté
par ce workflow.

Le `~` suit l’ordre de versions Debian : `0.1.4~dev.…` précède `0.1.4`. Après une
publication stable, passer la version de base au prochain numéro avant de
poursuivre le développement, par exemple `0.1.5`.

Les anciennes constructions utilisaient `0.1.3+git…`, qui est supérieur à
`0.1.3` pour Debian. Pour remplacer ces paquets sans rétrogradation, choisir une
prochaine version stable supérieure, par exemple `0.1.4`.

## Changer la version de base

Mettre le même numéro `X.Y.Z` dans les trois fichiers :

- `minttweaks/__init__.py` : variable `__version__` ;
- `debian/changelog` : en-tête de la nouvelle entrée, avec les changements et leur date ;
- `data/minttweaks.1` : numéro dans la première ligne du manuel.

Exécuter ensuite :

```bash
make test
make check
git diff --check
```

Le workflow vérifie les marqueurs avant de les modifier dans son checkout de
construction. Une préversion reçoit son suffixe dans ces trois fichiers ; le
paquet et l’archive des sources portent ainsi la même version. Une construction
stable conserve la version des sources. Aucun numéro généré n’est commité
automatiquement.

## Publier une version stable

1. Préparer le numéro et les notes de version, puis vérifier les sources.
2. Suivre la [recette Linux Mint](../validation/linux-mint.md) et remplir son
   [compte rendu](../validation/compte-rendu.md) : construction du paquet,
   installation, vrai GTK, refus polkit, simulation, entretien et restauration Samba.
3. Après validation et autorisation de publication, commiter et envoyer les
   sources sur `main`.
4. Créer un tag sur le commit validé, puis envoyer uniquement ce tag. Exemple
   pour une version de base `0.1.4`, depuis le commit voulu :

   ```bash
   git tag -a v0.1.4 -m "MintTweaks 0.1.4"
   git push origin v0.1.4
   ```

5. Vérifier le résultat réel du workflow, puis télécharger le `.deb`, les sources
   et `SHA256SUMS` de la Release. Vérifier les sommes de contrôle.

Le tag exprime la décision de publier une version stable ; le workflow ne prouve
pas à lui seul que la recette Linux Mint a été effectuée.

## Diffusion rapide vers le dépôt APT

Le job `update-apt-repository` est prévu après la publication réussie d’une
version **stable**. Il vérifie la Release et son unique paquet Debian attendu,
déclenche `Signed APT repository` sur `main` dans
`Masternaka/masternaka-repository`, puis attend la présence de cette version et
du même SHA-256 dans le manifeste public et vérifie le paquet téléchargé.
Les préversions ne déclenchent pas cette diffusion. La vérification ne force
aucune mise à jour des machines clientes et n’installe rien sur leurs systèmes.

Ce mécanisme ajoute un job Ubuntu standard par Release stable, sans nouvelle
planification et sans cache supplémentaire. Les runners standard des dépôts
publics sont [gratuits](https://docs.github.com/en/actions/concepts/billing-and-usage).
Le passage toutes les six heures du dépôt central est conservé comme rattrapage
pour les projets personnels distribués ; il reste sujet aux délais GitHub.
Helium et Zen sont installés directement depuis leurs sources officielles.

### Configuration unique

Créer un jeton personnel **fine-grained**, limité au seul dépôt
`Masternaka/masternaka-repository`, avec **Actions: Read and write** et une
expiration adaptée. L’enregistrer comme secret Actions
`APT_REPOSITORY_DISPATCH_TOKEN` dans **Masternaka/MintTweaks**. Aucun droit
d’administration ou d’écriture du code ni aucune clé privée APT n’est nécessaire
dans ce nouveau secret. Ne jamais le placer dans Git ou dans un message.

Le jeton `GITHUB_TOKEN` de MintTweaks ne permet pas d’écrire dans l’autre dépôt.
Voir les permissions de l’API [workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

### Vérification et reprise

La notification n’est pas assimilée à une publication APT réussie. Le job attend
jusqu’à dix minutes le manifeste attendu, puis vérifie le `.deb` public. En cas
de jeton absent/expiré, d’échec HTTP ou d’attente dépassée, il échoue explicitement
avec un lien vers les workflows du dépôt central. La Release GitHub déjà publiée
reste disponible ; elle n’est pas supprimée ou réécrite.

Corriger le secret ou l’erreur du dépôt APT et relancer **uniquement le job
échoué**. Ne pas relancer le job de publication de la Release stable existante,
qui refuse volontairement de la remplacer. Un déclenchement manuel du workflow
central sur `main` reste possible. Sur le client, `apt update` et l’installation
ou le gestionnaire de mises à jour restent nécessaires.

La disponibilité du `.deb` et son SHA-256 sont vérifiés depuis GitHub Pages ; les
signatures et le téléchargement APT sont validés par le workflow central. Ces
contrôles ne remplacent pas un essai réel de mise à jour sous Linux Mint.

## Relances et publications existantes

- Une nouvelle construction de développement possède un tag propre au numéro
  d’exécution et à la tentative. Relancer seulement son travail de publication
  peut remplacer ses fichiers ; le statut préversion est réappliqué.
- Une Release stable existante n’est jamais remplacée par le workflow. La
  relance échoue explicitement sans modifier ses fichiers ni ses métadonnées.
  Vérifier la publication existante avant de décider d’une nouvelle version.
- Les anciennes Releases déjà publiées ne sont pas reclassées par cette
  modification. Le dépôt APT central est géré séparément ; vérifier son état et
  sa configuration avant d’annoncer la disponibilité d’une version via APT.

Références : [options GitHub CLI des Releases](https://cli.github.com/manual/gh_release_create)
et [ordre des versions Debian](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version).
