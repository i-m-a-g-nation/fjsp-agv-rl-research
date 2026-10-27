"""A fresh Git checkout must preserve the byte identities of live references."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('autocrlf', ['false', 'true'])
def test_fresh_checkout_matches_bound_reference_source_bytes(tmp_path, autocrlf):
    git = shutil.which('git')
    if git is None:
        pytest.skip('Git is required to exercise checkout conversion')
    expected = {}
    for name in ('exp_025_neural_policy_phase1_v2', 'exp_026_validation_iteration_phase1_v2'):
        manifest = json.loads((ROOT / 'experiments/results' / name / 'manifest.json').read_text(encoding='utf-8-sig'))
        for relative, digest in manifest['source_hashes'].items():
            assert relative not in expected or expected[relative] == digest
            expected[relative] = digest
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    attributes = tmp_path / 'empty-global-attributes'
    attributes.write_bytes(b'')

    def run(*args):
        return subprocess.run([git, '-c', f'core.autocrlf={autocrlf}', '-c', 'core.eol=lf',
            '-c', f'core.attributesFile={attributes}', '-c', 'core.safecrlf=false', *args],
            cwd=checkout, check=True, capture_output=True)

    run('init', '--quiet')
    shutil.copyfile(ROOT / '.gitattributes', checkout / '.gitattributes')
    for relative in expected:
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # These text sources are stored as LF Git blobs. Start from that form,
        # not the developer's possibly already-converted working-tree bytes.
        target.write_bytes((ROOT / relative).read_bytes().replace(b'\r\n', b'\n'))
    run('add', '--all')
    for relative in expected:
        (checkout / relative).unlink()
    run('checkout-index', '--all')
    mismatches = [relative for relative, digest in expected.items()
                  if hashlib.sha256((checkout / relative).read_bytes()).hexdigest() != digest]
    assert not mismatches, f'Checkout changed source bytes bound to reference evidence: {mismatches}'
