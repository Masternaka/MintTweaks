"""Curated terminal tools; IDs, APT packages and executable names are distinct."""
from dataclasses import dataclass
from ...i18n import _


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    package: str
    binaries: tuple
    category: str
    description: str
    example: str
    website: str
    starter: bool = False


CATEGORIES = (
    ('navigation', _('Navigation and search')),
    ('files', _('Files and disk space')),
    ('development', _('Development and data')),
    ('sessions', _('Sessions and monitoring')),
    ('shell', _('Shell enhancements')),
    ('base', _('Shells and terminal applications')),
)

CATALOG = (
    Tool('fzf', 'fzf', 'fzf', ('fzf',), 'navigation', _('Interactive fuzzy search for files and command output. Managed shell shortcuts are available.'), 'find . -type f | fzf', 'https://github.com/junegunn/fzf', True),
    Tool('zoxide', 'zoxide', 'zoxide', ('zoxide',), 'navigation', _('Jump to frequently used directories. Managed integration enables the z shortcut.'), 'zoxide query minttweaks', 'https://github.com/ajeetdsouza/zoxide', True),
    Tool('ripgrep', 'ripgrep', 'ripgrep', ('rg',), 'navigation', _('Fast text search across files, respecting ignore rules.'), 'rg "TODO" .', 'https://github.com/BurntSushi/ripgrep', True),
    Tool('fd', 'fd', 'fd-find', ('fdfind', 'fd'), 'navigation', _('Find files by name. The Ubuntu/Mint package commonly provides fdfind.'), 'fdfind README', 'https://github.com/sharkdp/fd', True),
    Tool('bat', 'bat', 'bat', ('batcat', 'bat'), 'files', _('Read files with syntax highlighting. The Ubuntu/Mint command is commonly batcat.'), 'batcat README.md', 'https://github.com/sharkdp/bat', True),
    Tool('eza', 'eza', 'eza', ('eza',), 'files', _('List files with colors, tree views and Git information.'), 'eza --long --git', 'https://github.com/eza-community/eza', True),
    Tool('tree', 'tree', 'tree', ('tree',), 'files', _('Display a directory tree.'), 'tree -L 2', 'https://oldmanprogrammer.net/source.php?dir=projects/tree'),
    Tool('ncdu', 'ncdu', 'ncdu', ('ncdu',), 'files', _('Explore disk usage interactively; its delete action can remove files.'), 'ncdu .', 'https://dev.yorhel.nl/ncdu'),
    Tool('duf', 'duf', 'duf', ('duf',), 'files', _('Show free and used disk space in a readable table.'), 'duf', 'https://github.com/muesli/duf'),
    Tool('git', 'Git', 'git', ('git',), 'development', _('Track source changes and work with Git repositories.'), 'git status', 'https://git-scm.com/'),
    Tool('lazygit', 'lazygit', 'lazygit', ('lazygit',), 'development', _('Interactive Git interface inside the terminal.'), 'lazygit', 'https://github.com/jesseduffield/lazygit'),
    Tool('delta', 'delta', 'git-delta', ('delta',), 'development', _('Readable, highlighted diffs. Managed integration can make it the Git pager in your shell.'), 'git diff --no-color | delta', 'https://github.com/dandavison/delta'),
    Tool('neovim', 'Neovim', 'neovim', ('nvim',), 'development', _('Extensible terminal text editor.'), 'nvim README.md', 'https://neovim.io/'),
    Tool('jq', 'jq', 'jq', ('jq',), 'development', _('Read, filter and transform JSON data.'), "jq '.' file.json", 'https://jqlang.org/'),
    Tool('curl', 'curl', 'curl', ('curl',), 'development', _('Transfer data and inspect HTTP responses.'), 'curl --head https://linuxmint.com', 'https://curl.se/'),
    Tool('wget', 'Wget', 'wget', ('wget',), 'development', _('Download files from the command line.'), 'wget --help', 'https://www.gnu.org/software/wget/'),
    Tool('tmux', 'tmux', 'tmux', ('tmux',), 'sessions', _('Keep terminal sessions with multiple panes and windows.'), 'tmux new -s work', 'https://github.com/tmux/tmux', True),
    Tool('btop', 'btop', 'btop', ('btop',), 'sessions', _('Monitor CPU, memory, disks, network and processes.'), 'btop', 'https://github.com/aristocratos/btop', True),
    Tool('htop', 'htop', 'htop', ('htop',), 'sessions', _('Inspect and manage running processes interactively.'), 'htop', 'https://htop.dev/'),
    Tool('fastfetch', 'Fastfetch', 'fastfetch', ('fastfetch',), 'sessions', _('Display a system summary in the terminal.'), 'fastfetch', 'https://github.com/fastfetch-cli/fastfetch'),
    Tool('tldr', 'tldr', 'tldr', ('tldr',), 'shell', _('Short command examples. The client may need to download its page cache.'), 'tldr tar', 'https://github.com/tldr-pages/tldr', True),
    Tool('direnv', 'direnv', 'direnv', ('direnv',), 'shell', _('Load project environment variables after explicit approval. A managed shell hook is available.'), 'direnv status', 'https://direnv.net/'),
    Tool('atuin', 'Atuin', 'atuin', ('atuin',), 'shell', _('Search shell history. Managed local integration is available; account sync remains optional and manual.'), 'atuin search', 'https://atuin.sh/'),
    Tool('bash-completion', 'bash-completion', 'bash-completion', (), 'shell', _('Additional Bash command completions. Managed activation is available for Bash.'), '', 'https://github.com/scop/bash-completion'),
    Tool('zsh-autosuggestions', 'zsh-autosuggestions', 'zsh-autosuggestions', (), 'shell', _('Suggest Zsh commands from history. Managed activation is available for Zsh.'), '', 'https://github.com/zsh-users/zsh-autosuggestions'),
    Tool('zsh-syntax-highlighting', 'zsh-syntax-highlighting', 'zsh-syntax-highlighting', (), 'shell', _('Highlight commands while typing in Zsh. Managed activation is available for Zsh.'), '', 'https://github.com/zsh-users/zsh-syntax-highlighting'),
    Tool('starship', 'Starship', 'starship', ('starship',), 'shell', _('Customizable prompt for Bash, Zsh and Fish. Managed activation is available in Shell integrations.'), 'starship --version', 'https://starship.rs/guide/'),
    Tool('bash', 'Bash', 'bash', ('bash',), 'base', _('Traditional shell, normally already installed on Mint.'), 'bash --version', 'https://www.gnu.org/software/bash/'),
    Tool('zsh', 'Zsh', 'zsh', ('zsh',), 'base', _('Shell with extensive completion and customization options.'), 'zsh --version', 'https://www.zsh.org/'),
    Tool('fish', 'Fish', 'fish', ('fish',), 'base', _('Interactive shell with built-in suggestions and syntax highlighting.'), 'fish --version', 'https://fishshell.com/'),
    Tool('kitty', 'Kitty', 'kitty', ('kitty',), 'base', _('Terminal application with tabs, layouts and GPU rendering.'), 'kitty --version', 'https://sw.kovidgoyal.net/kitty/'),
    Tool('alacritty', 'Alacritty', 'alacritty', ('alacritty',), 'base', _('GPU-rendered terminal application.'), 'alacritty --version', 'https://alacritty.org/'),
)
TOOL_BY_ID = {tool.id: tool for tool in CATALOG}
TOOLS = tuple(TOOL_BY_ID)
