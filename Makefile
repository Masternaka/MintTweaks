# MintTweaks - installation and development helpers.
#
#   make            run the test suite
#   make run        start the application from the source tree
#   make translations   rebuild the compiled catalogues
#   sudo make install
#   sudo make uninstall

PREFIX   ?= /usr
DESTDIR  ?=
BINDIR    = $(DESTDIR)$(PREFIX)/bin
LIBDIR    = $(DESTDIR)$(PREFIX)/lib
SHAREDIR  = $(DESTDIR)$(PREFIX)/share
APPDIR    = $(DESTDIR)$(PREFIX)/share/applications
ICONDIR   = $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps
MANDIR    = $(DESTDIR)$(PREFIX)/share/man/man1

PKG       = minttweaks
PYTHON   ?= python3
INSTALL  ?= install
LANGUAGES = fr

MO_FILES  = $(foreach lang,$(LANGUAGES),$(PKG)/locale/$(lang)/LC_MESSAGES/minttweaks.mo)

.PHONY: all test check run translations pot install uninstall clean help

all: test

help:
	@sed -n '2,8p' Makefile | sed 's/^# \{0,1\}//'

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

# Syntax-check everything, keep the catalogue and translations in sync.
check:
	PYTHONPYCACHEPREFIX=$${TMPDIR:-/tmp}/mtk-pycache $(PYTHON) -m compileall -q $(PKG) tests data/mtk-root tools
	$(PYTHON) tools/extract_strings.py --check
	$(PYTHON) tools/compile_mo.py --check po/fr.po
	$(MAKE) translations
	@echo "check: ok"

# Regenerate po/minttweaks.pot and the source references of every catalogue.
pot:
	$(PYTHON) tools/extract_strings.py --refresh

translations: $(MO_FILES)

$(PKG)/locale/%/LC_MESSAGES/minttweaks.mo: po/%.po tools/compile_mo.py
	$(PYTHON) tools/compile_mo.py $< $@

run:
	./bin/minttweaks

install: translations
	$(INSTALL) -d $(LIBDIR)/$(PKG)
	cp -r $(PKG) $(LIBDIR)/$(PKG)/
	$(INSTALL) -m 0755 data/mtk-root $(LIBDIR)/$(PKG)/mtk-root
	$(INSTALL) -d $(BINDIR)
	$(INSTALL) -m 0755 bin/minttweaks $(BINDIR)/minttweaks
	$(INSTALL) -d $(APPDIR)
	$(INSTALL) -m 0644 data/minttweaks.desktop $(APPDIR)/minttweaks.desktop
	$(INSTALL) -d $(ICONDIR)
	$(INSTALL) -m 0644 data/minttweaks.svg $(ICONDIR)/minttweaks.svg
	$(INSTALL) -d $(MANDIR)
	$(INSTALL) -m 0644 data/minttweaks.1 $(MANDIR)/minttweaks.1
	-find $(LIBDIR)/$(PKG) -name '__pycache__' -type d -exec rm -rf {} +
	@echo
	@echo "Installed. Start it with 'minttweaks' or from the menu."
	@echo "If the menu entry is missing, run: gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor 2>/dev/null || true"

uninstall:
	rm -rf $(LIBDIR)/$(PKG)
	rm -f $(BINDIR)/minttweaks
	rm -f $(APPDIR)/minttweaks.desktop
	rm -f $(ICONDIR)/minttweaks.svg
	rm -f $(MANDIR)/minttweaks.1
	@echo "Removed. Your ~/.local/share/minttweaks data (logs and smb.conf backups) was kept."

clean:
	-rm -rf $(PKG)/locale
	-find . -name '__pycache__' -type d -exec rm -rf {} +
	-find . -name '*.pyc' -delete
