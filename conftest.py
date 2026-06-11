"""Pytest bootstrap for the repository.

The maintained package lives under ``src/`` (see
``[tool.setuptools.package-dir]`` in ``pyproject.toml``), so ``src`` has to be
on ``sys.path`` for ``import muse_tmr`` to resolve when running ``pytest``
directly from a checkout without an editable install.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")
if os.path.isdir(_SRC_DIR) and _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
