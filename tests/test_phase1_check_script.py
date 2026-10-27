from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not (shutil.which('powershell') or shutil.which('pwsh')), reason='PowerShell unavailable')
def test_local_check_script_stops_when_a_python_check_fails(tmp_path):
    """Run the real orchestration with only its external Python command replaced."""
    fake = tmp_path / 'failing-python.ps1'
    fake.write_text('Write-Output "deliberate check failure"\nexit 7\n', encoding='utf-8')
    script = Path('scripts/run_checks.ps1').read_text(encoding='utf-8')
    script = script.replace('$PythonExe = Join-Path $EnvPath "python.exe"',
                            "$PythonExe = '" + str(fake).replace("'", "''") + "'")
    copied = tmp_path / 'scripts' / 'run_checks.ps1'
    copied.parent.mkdir()
    copied.write_text(script, encoding='utf-8')
    run = subprocess.run([shutil.which('powershell') or shutil.which('pwsh'),
                          '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(copied)],
                         capture_output=True, text=True, timeout=30)
    assert run.returncode != 0
    assert 'All local checks completed successfully' not in run.stdout
    assert run.stdout.count('deliberate check failure') == 1
