# MintTweaks

A system tweaking tool for **Linux Mint**, in the spirit of the
[ArchLinux Tweak Tool](https://github.com/kirodubes/archlinux-tweak-tool): one
window for the system chores that Mint otherwise spreads across `apt`, `systemctl`,
`journalctl` and `smb.conf`.

MintTweaks is written in **Python 3 + GTK 3** on purpose: GTK 3 is what Cinnamon
uses, it is already installed on every supported Mint release, and the
application inherits the Mint-Y theme instead of looking foreign next to
Cinnamon's own settings panels.

Linux Mint ships excellent first-party tools (Update Manager, Driver Manager,
Timeshift, Backup Tool). MintTweaks does not replace them: it covers what has no
graphical home yet.

## What it does today (v0.1)

### Maintenance
- Real sizes for the APT cache, the system journal, thumbnails and the trash.
- **Preview of `apt-get autoremove` before anything is removed** — you see the
  list of packages, then you decide.
- One-click cleanup tasks: orphaned packages, obsolete `.deb` files, broken
  dependencies, journal vacuum (by size or by age), thumbnail cache, trash,
  unused Flatpak runtimes.
- Kernel management that refuses to shoot itself in the foot: the running kernel
  and the newest one are never offered for removal, and every related package
  of a selected kernel is removed in a single `apt-get purge`.

### Services
- Every `*.service` unit with its runtime state and its startup state, in one
  filterable table.
- Start / stop / restart / enable / disable, with a confirmation for the
  disruptive ones.
- The unit's journal, with a *Read as administrator* fallback when the
  unprivileged journal is empty.
- Boot analysis: `systemd-analyze` summary, slowest units and the critical chain.

### Samba
- Install `samba`, `smbclient` and `cifs-utils` from the app.
- Full share management: create, edit, rename, delete, with folder picker,
  browseable/read-only/guest toggles, `valid users`, `write list`, masks and
  `force group`.
- Samba account management: create/change password, enable, disable, delete —
  passwords travel on `smbpasswd`'s **stdin**, never on a command line.
- A raw `smb.conf` editor with **`testparm` validation**, duplicate cleanup, and
  a *Restore a backup* picker.
- Service and firewall helpers: enable and start `smbd`/`nmbd`, reload the
  configuration, allow Samba through `ufw`, list active connections.

The interface is translated into **French**; see [Languages](#languages).

## Requirements

| | |
|---|---|
| Distribution | Linux Mint 20, 21 or 22 (Cinnamon) |
| Runtime | `python3` ≥ 3.8, `python3-gi`, `gir1.2-gtk-3.0` (installed by default) |
| Privileges | `pkexec` / polkit (`policykit-1`, installed by default) |
| For the Samba module | `samba`, `smbclient`, `cifs-utils` (the app installs them) |

## Install

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 policykit-1
git clone https://github.com/<you>/MintTweaks.git
cd MintTweaks
make test          # 184 tests, no display needed
sudo make install
minttweaks
```

`make install` puts the package in `/usr/lib/minttweaks` (with the compiled
translations), the launcher in `/usr/bin/minttweaks`, the privileged helper next
to the package, and the menu entry, icon and man page in `/usr/share`.
`sudo make uninstall` removes them and keeps your backups and logs.

Run it from a checkout with `./bin/minttweaks` — no installation needed.

## Build a Debian package

```bash
sudo apt install debhelper dh-python devscripts
# put your real name and address in debian/control (Maintainer) and debian/changelog
dpkg-buildpackage -us -uc -b
sudo apt install ../minttweaks_0.1.0_all.deb
```

The packaging is deliberately thin: `debian/rules` calls the same `make install`
a source install uses, so there is only one layout to maintain. `make check`
validates the packaging from any machine (no `dpkg` required):

- every file debhelper expects is present, `debian/rules` is an executable
  makefile with tab-indented recipes;
- `debian/control` declares `python3-gi`, `gir1.2-gtk-3.0` and `policykit-1`;
- the changelog version matches `minttweaks/__init__.py`;
- the desktop entry's `Exec`/`Icon` point at files the Makefile really installs;
- `make uninstall` undoes exactly what `make install` did.

## Languages

The source strings are English; French ships as a compiled catalogue.

```bash
make pot            # regenerate po/minttweaks.pot from the source
make translations   # compile po/*.po into minttweaks/locale/<lang>/LC_MESSAGES/
make check          # fails if the template is stale or a string is untranslated
```

To add a language, copy `po/fr.po` to `po/de.po`, translate, add the code to
`LANGUAGES` in the `Makefile`, and run `make translations`. `--lang de` forces
it for one run, and `MTK_LOCALEDIR` points at a catalogue directory.

Two rules keep this maintainable:

- every user-visible string is wrapped in `_()`; `tools/extract_strings.py`
  refuses f-strings, because they cannot be extracted;
- strings built at import time (the task registry) store the English msgid and
  translate on access, so the catalogue loaded at startup is always the one used.

The **output panel stays in English**: it is a technical transcript of commands,
`apt` and `testparm` output, and translating it would only make bug reports
harder to read.

## How privileges work

MintTweaks runs as you. It never keeps root and never runs a shell. The few
actions that need administrator rights are handed to `pkexec`, so the password
dialog is the standard polkit one that your Cinnamon session already provides.

Replacing `/etc/samba/smb.conf` goes through a deliberately narrow helper,
`data/mtk-root`, whose entire job is that one file:

- it only accepts a candidate that is a regular file, owned by the invoking
  user, smaller than 1 MiB, and that looks like an `smb.conf`;
- it runs `testparm` **as root** before touching anything (the GUI also
  validates first, so a bad file is normally rejected without a password prompt);
- it copies the current file to `/var/backups/samba/smb.conf.<timestamp>`
  (last 20 kept) and forces `root:root 0644` on the result;
- it reloads `smbd` in the same privileged call, so a save costs a single
  authorisation.

## Safety model

- **No shell, ever.** Every command is an argv list handed to `subprocess`
  without `shell=True`; there is a test asserting it. Share names, paths and
  unit names are validated against strict patterns before they reach a command.
- **Validate, then write.** `smb.conf` goes through `testparm` twice (GUI side
  and root side) and is never written blind; a rejected file leaves memory and
  disk untouched.
- **Backups before changes.** Samba configuration is copied to
  `~/.local/share/minttweaks/backups/` (user-readable, restorable from the UI)
  before each save.
- **Previews for destructive work.** `apt-get -s` is free, so orphan removal is
  always previewed; kernels are listed with an explicit checkbox each.
- **User data is never touched as root.** Thumbnails and trash are cleaned as
  you, and symlinks are unlinked, never followed.
- **Refusals are explicit.** The running kernel cannot be purged, the filesystem
  root cannot be exported, and unknown units are not driven.

## Development

```bash
make test                                  # unit tests (unittest, no pytest needed)
make check                                 # syntax, catalogue and packaging checks
make translations                          # rebuild po/*.po into .mo
MTK_DRY_RUN=1 ./bin/minttweaks             # print commands instead of running them
MTK_ROOT_CMD="sudo -n" ./bin/minttweaks    # use a different escalation command
./bin/minttweaks --lang fr                 # force the interface language
```

The test suite runs anywhere, including on a machine without GTK: the system
layer takes its commands through an injectable `Runner` (see `tests/fakes.py`),
and `tests/fakegi.py` stubs PyGObject so the widget modules can be imported,
instantiated and fed real backend data.

```
minttweaks/
├── app.py                     Gtk.Application, CLI flags, language loading
├── i18n.py                    gettext wrapper (`_`, `install`, `reset`)
├── core/
│   ├── runner.py              Command/Result + injectable Runner
│   ├── privilege.py           pkexec escalation
│   ├── smbconf.py             round-trip safe smb.conf model
│   ├── logs.py, paths.py
├── modules/
│   ├── maintenance/           backend.py + page.py
│   ├── services/              backend.py + page.py
│   └── samba/                 backend.py + page.py
└── ui/                        window.py, widgets.py, style.css
data/                          .desktop, icon, man page, mtk-root helper
po/                            minttweaks.pot + fr.po
tools/                         extract_strings.py, compile_mo.py
debian/                        debhelper packaging
docs/                          prioritised backlog (ideas.md)
tests/                         unittest suite + fakes + gi stub
```

Each module keeps its logic in `backend.py` (no GTK import, fully testable) and
its widgets in `page.py`. If you want to add a module: write a backend, write a
`Page` subclass declaring `page_name` / `page_title` / `page_icon`, and add the
class to `ui/window.py:PAGE_CLASSES`.

## Roadmap

The detailed, prioritised backlog lives in [docs/ideas.md](docs/ideas.md)
(written in French). Short version:

- [ ] **System health check** — one button that audits the machine and proposes fixes
- [ ] **Timeshift in Maintenance** — a restore point before destructive cleanup
- [ ] **Aggregated journal** — errors since boot, kernel messages
- [ ] **`sysctl` tweaks** — dedicated drop-in, original value shown, revert to default
- [ ] **Firewall (`ufw`)** and **Flatpak permissions** modules
- [ ] **Hardware page** — Secure Boot, battery health, firmware
- [ ] More translations (the catalogue is ready for them)

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).

---

## En français

MintTweaks est un outil de réglages pour Linux Mint, inspiré d'ArchLinux Tweak
Tool, écrit en Python 3 + GTK 3 pour rester natif sous Cinnamon.

Trois modules pour l'instant :

1. **Entretien** : tailles réelles (cache APT, journal, miniatures, corbeille),
   aperçu des paquets orphelins avant suppression, tâches de nettoyage, et
   suppression prudente des anciens noyaux (le noyau courant et le plus récent
   sont toujours conservés).
2. **Services** : liste filtrable des unités systemd, démarrage/arrêt/
   activation, journaux par service, analyse du temps de démarrage.
3. **Samba** : installation, gestion complète des partages et des comptes,
   éditeur de `smb.conf` validé par `testparm`, sauvegardes et restauration.

L'interface est **traduite en français** : elle suit la locale du système, et
`--lang fr` permet de la forcer. Le panneau de sortie reste en anglais, c'est un
journal technique de commandes.

Installation : `sudo apt install python3-gi gir1.2-gtk-3.0` puis
`sudo make install`, ou directement `./bin/minttweaks` depuis le dépôt.
Paquet Debian : `dpkg-buildpackage -us -uc -b` (pensez à mettre votre nom et
votre adresse dans `debian/control` avant).

Aucune commande ne passe par un shell, les mots de passe Samba passent par
l'entrée standard, et `smb.conf` est validé avant chaque écriture.
