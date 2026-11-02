"""Personal list imported from the user-supplied app.md.

Use one Application per requested program, with an exact native APT package name.
Do not put third-party sources, URLs, shell commands, Flatpaks or suggestions here.
"""
from dataclasses import dataclass
from ...i18n import _


@dataclass(frozen=True)
class Application:
    id: str
    name: str
    package: str
    category: str
    description: str = ''
    alternatives: tuple = ()


CATALOG = (
    Application('catfish', 'Catfish', 'catfish', _('Utilities')),
    Application('gparted', 'GParted', 'gparted', _('Utilities')),
    Application('qbittorrent', 'qBittorrent', 'qbittorrent', _('Utilities')),
    Application('transmission-gtk', 'Transmission', 'transmission-gtk', _('Utilities')),
    Application('lshw', 'lshw', 'lshw', _('Utilities')),
    Application('fwupd', 'fwupd', 'fwupd', _('Utilities')),
    Application('7zip', '7-Zip', '7zip', _('Utilities'), description=_("Uses p7zip-full on distributions without the 7zip package."), alternatives=('p7zip-full',)),
    Application('unzip', 'Unzip', 'unzip', _('Utilities')),
    Application('stow', 'GNU Stow', 'stow', _('Utilities')),
    Application('fontconfig', 'Fontconfig', 'fontconfig', _('Utilities')),
    Application('font-manager', 'Font Manager', 'font-manager', _('Utilities')),
    Application('flameshot', 'Flameshot', 'flameshot', _('Utilities')),
    Application('btop', 'btop', 'btop', _('Terminal utilities')),
    Application('fastfetch', 'Fastfetch', 'fastfetch', _('Terminal utilities')),
    Application('git', 'Git', 'git', _('Terminal utilities')),
    Application('curl', 'curl', 'curl', _('Terminal utilities')),
    Application('wget', 'Wget', 'wget', _('Terminal utilities')),
    Application('ranger', 'Ranger', 'ranger', _('Terminal utilities')),
    Application('strawberry', 'Strawberry', 'strawberry', _('Multimedia')),
    Application('vlc', 'VLC', 'vlc', _('Multimedia')),
    Application('mpv', 'mpv', 'mpv', _('Multimedia')),
    Application('qemu', 'QEMU', 'qemu', _('Virtualization'), description=_("Uses qemu-system when the qemu package is unavailable."), alternatives=('qemu-system',)),
    Application('virt-manager', 'Virtual Machine Manager', 'virt-manager', _('Virtualization')),
    Application('distrobox', 'Distrobox', 'distrobox', _('Virtualization')),
    Application('podman', 'Podman', 'podman', _('Virtualization')),
    Application('kitty', 'Kitty', 'kitty', _('Terminal')),
    Application('micro', 'Micro', 'micro', _('Development')),
    Application('meld', 'Meld', 'meld', _('Development')),
    Application('fonts-cascadia-code', 'Cascadia Code', 'fonts-cascadia-code', _('Fonts')),
    Application('fonts-firacode', 'Fira Code', 'fonts-firacode', _('Fonts')),
    Application('fonts-hack', 'Hack', 'fonts-hack', _('Fonts')),
    Application('fonts-jetbrains-mono', 'JetBrains Mono', 'fonts-jetbrains-mono', _('Fonts')),
    Application('fonts-noto', 'Noto', 'fonts-noto', _('Fonts')),
    Application('fonts-font-awesome', 'Font Awesome', 'fonts-font-awesome', _('Fonts')),
)
