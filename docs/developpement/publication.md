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
