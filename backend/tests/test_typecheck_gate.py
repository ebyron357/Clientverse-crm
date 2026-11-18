"""The formerly reporting-only modules cannot reintroduce type debt silently."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(('output', 'returncode', 'expected'), [
    ('legacy_route.py:4: error: Missing tenant context  [arg-type]\nFound 1 error in 1 file', 1, 1),
    ('Success: no issues found in 37 source files', 0, 0),
    ('mypy: configuration could not be read', 2, 2),
])
def test_type_gate_enforces_all_checked_modules(tmp_path, monkeypatch, output, returncode, expected):
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'typecheck.py'
    spec = importlib.util.spec_from_file_location('crm_typecheck_gate', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / 'pyproject.toml').write_text(
        '[[tool.mypy.overrides]]\nmodule = ["strict_module"]\ndisallow_incomplete_defs = true\n')
    monkeypatch.setattr(module.sys, 'argv', [str(script), str(tmp_path)])
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        stdout=output, stderr='', returncode=returncode))
    assert module.main() == expected
