# MintTweaks

Outil de réglages, d’entretien et de personnalisation pour **Linux Mint Cinnamon**,
écrit en Python 3 et GTK 3. Il complète les outils de Mint ; Timeshift reste géré
par son application dédiée.

## Modules

| Module | Fonctions |
| --- | --- |
| [Accueil](docs/guides/administration.md#accueil) | Résumé du système et diagnostics en lecture seule |
| [Entretien](docs/guides/administration.md#entretien) | Espace disque, nettoyage, aperçu APT et anciens noyaux |
| [Services](docs/guides/administration.md#services) | Services systemd, journaux et analyse du démarrage |
| [Samba](docs/guides/administration.md#samba) | Partages, comptes, validation et restauration de configuration |
| [Firefox](docs/guides/administration.md#firefox) | Catalogue d’extensions et politique du navigateur natif |
| [Profils Cinnamon](docs/guides/profils-cinnamon.md) | Capture, application et restauration de sept réglages d’apparence |
| [Après installation](docs/guides/assistant-apres-installation.md) | Parcours facultatif avec progression déclarée par l’utilisateur |
| [Logiciels natifs](docs/guides/logiciels-natifs.md) | Helium, Brave et Zen depuis les sources APT tierces attendues |
| [Shells et terminaux](docs/guides/shells-et-terminaux.md) | 32 outils, intégrations, réglages personnels, alias et export/import ; Kitty et Alacritty |

Les changements sont précédés de confirmations et, pour les configurations
gérées, de sauvegardes. Les opérations qui modifient le système utilisent une
réservation commune ; les droits administrateur passent par polkit.

**Validation :** les tests automatisés fonctionnent sans GTK et sans modifier le
système. Ils ne prouvent pas le comportement réel sous Mint. Les essais GTK,
installations, nouvelles sessions de shell et restaurations restent à consigner
dans la [recette Linux Mint](docs/validation/linux-mint.md).

## Installation depuis les sources

Cibles prévues : Linux Mint Cinnamon, familles 20, 21 et 22, à valider séparément.
Prérequis : Python ≥ 3.8, `python3-gi`, `gir1.2-gtk-3.0` et polkit.

Sur la machine Mint :

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 policykit-1
git clone https://github.com/Masternaka/MintTweaks.git
cd MintTweaks
make test
make check
sudo make install
minttweaks
```

Le lanceur est installé dans `/usr/bin`, le paquet et ses traductions dans
`/usr/lib/minttweaks`, et les ressources de bureau dans `/usr/share`.
`sudo make uninstall` retire l’application en conservant les données utilisateur.

Depuis le dépôt, `./bin/minttweaks` lance l’application sans installation.
L’interface suit la langue du système ; `--lang fr` force le français.

## Paquets et publications

Les fichiers `.deb`, leurs sources et `SHA256SUMS` sont distribués dans les
[Releases GitHub](https://github.com/Masternaka/MintTweaks/releases).
Vérifier les sommes de contrôle avant installation du paquet téléchargé :

```bash
sha256sum --ignore-missing --check SHA256SUMS
sudo apt install ./minttweaks_*_all.deb
```

Le workflow prévoit des préversions de développement sur `main` et des versions
stables sur tag explicite `vX.Y.Z`. Une préversion ne vaut pas validation sous
Mint. Voir la [procédure de publication](docs/developpement/publication.md).
Le [dépôt APT central](https://github.com/Masternaka/masternaka-repository)
est un projet séparé ; sa disponibilité doit être vérifiée dans ce projet.

## Développement

```bash
make test                         # Tests unittest, sans installation système
make check                        # Syntaxe, scripts et traductions
make pot                          # Actualiser le modèle gettext
./bin/minttweaks --dry-run         # Simulation des modifications
./bin/minttweaks --lang fr         # Interface en français
```

Le code se trouve dans `minttweaks/`, les tests dans `tests/`, les ressources
installées dans `bin/` et `data/`, et les outils de construction dans `tools/`
et `debian/`. Les chemins attendus par les lanceurs et l’empaquetage sont conservés.

## Documentation

- [Index des guides et références](docs/README.md)
- [Développement, architecture et privilèges](docs/developpement/architecture.md)
- [Recette Mint](docs/validation/linux-mint.md) et [compte rendu](docs/validation/compte-rendu.md)
- [Feuille de route](docs/roadmap.md)

## Licence

[GPL-3.0-or-later](LICENSE).
