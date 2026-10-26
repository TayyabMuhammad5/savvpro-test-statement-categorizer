#!/usr/bin/env python3
"""Universal test runner for Focal & Folio Statement Categorizer backend."""
from __future__ import annotations

import importlib.abc
import importlib.util
import pathlib
import sys
import unittest


class DirectStatFinder(importlib.abc.MetaPathFinder):
    """Ensures package discovery works across both standard filesystems and FUSE mounts."""

    def find_spec(self, fullname: str, path=None, target=None):
        parts = fullname.split(".")
        base = pathlib.Path(__file__).resolve().parent
        pkg_init = base.joinpath(*parts, "__init__.py")
        if pkg_init.exists():
            return importlib.util.spec_from_file_location(
                fullname, str(pkg_init), submodule_search_locations=[str(pkg_init.parent)]
            )
        mod_file = base.joinpath(*parts).with_suffix(".py")
        if mod_file.exists():
            return importlib.util.spec_from_file_location(fullname, str(mod_file))
        return None


def main() -> int:
    sys.meta_path.insert(0, DirectStatFinder())
    from tests import test_api, test_brain, test_parser

    suite = unittest.TestSuite()
    for mod in (test_brain, test_parser, test_api):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(mod))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
