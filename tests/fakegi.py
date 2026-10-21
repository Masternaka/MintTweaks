"""A stand-in for PyGObject.

GTK is not installed on a development machine that is not running Linux Mint, so
the UI modules cannot normally be imported at all.  This stub provides just
enough of ``gi`` to import them: constant namespaces behave like objects,
widget classes behave like classes, and every call returns another stub.

It is *not* a GTK emulator.  It cannot tell you whether a dialog looks right; it
can tell you that the modules import, that the page classes declare their
metadata and that no name is misspelled at module scope.  Those are exactly the
mistakes that would otherwise only surface on the target machine.
"""

from __future__ import annotations

import sys
import types
from typing import Any, Optional


class _Meta(type):
    """Makes ``Gtk.Orientation.VERTICAL`` and ``Gtk.Box`` both work."""

    def __getattr__(cls, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        value = _Meta(name, (_StubBase,), {"_fake_gtk_class": True})
        setattr(cls, name, value)
        return value

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls.__dict__.get("_fake_gtk_class", False):
            # A faked widget: return something that swallows every call.
            # ``object.__new__`` avoids re-entering this method forever.
            return object.__new__(cls)
        # A real class of ours that merely *derives* from a faked widget
        # (Page, MainWindow, ...): instantiate it normally so __init__ runs.
        return super().__call__(*args, **kwargs)

    def __repr__(cls) -> str:
        return f"<stub {cls.__name__}>"


class _StubBase(metaclass=_Meta):
    """Base for every faked widget."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._args = args
        self._kwargs = kwargs

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _StubBase()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return _StubBase()

    def __repr__(self) -> str:
        return "<stub instance>"

    def __bool__(self) -> bool:
        return True

    # Containers: GTK returns lists and supports subscripts, so the stub has to
    # be iterable and subscriptable even though it holds nothing.
    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def __getitem__(self, _key: Any) -> Any:
        return _StubBase()

    def __setitem__(self, _key: Any, _value: Any) -> None:
        return None


def _repository_getattr(name: str) -> Any:
    if name.startswith("__"):
        raise AttributeError(name)
    value = _Meta(name, (_StubBase,), {"_fake_gtk_class": True})
    setattr(sys.modules["gi.repository"], name, value)
    return value


class FakeGI(types.ModuleType):
    pass


def install(force: bool = False) -> bool:
    """Install the stub. Returns False when the real PyGObject is present."""
    existing = sys.modules.get("gi")
    if existing is not None and not force and not isinstance(existing, FakeGI):
        return False

    gi_module = FakeGI("gi")
    gi_module.require_version = lambda *_args, **_kwargs: None
    gi_module.require_versions = lambda *_args, **_kwargs: None

    repository = FakeGI("gi.repository")
    repository.__getattr__ = _repository_getattr  # type: ignore[attr-defined]
    gi_module.repository = repository

    sys.modules["gi"] = gi_module
    sys.modules["gi.repository"] = repository
    return True
