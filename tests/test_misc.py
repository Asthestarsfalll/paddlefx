from __future__ import annotations

import paddlefx


def test_version():
    assert paddlefx.__version__ != '0.0.0.unknown'
