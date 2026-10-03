from pathlib import Path
import subprocess
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_sensitive_files.py"


@pytest.mark.parametrize(
    "name, content",
    [
        ("credentials.bin", b"SQLite format 3\x00SYNTHETIC_CONTENT"),
        (".env.production", b"SYNTHETIC_SECRET=value"),
        ("private.txt", b"-----BEGIN " + b"PRIVATE KEY-----\nSYNTHETIC_CONTENT"),
    ],
)
def test_guard_rejects_staged_secrets_without_displaying_contents(
    tmp_path, name, content
):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / name).write_bytes(content)
    subprocess.run(["git", "add", name], cwd=tmp_path, check=True)
    result = subprocess.run(
        ["python3", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert name in result.stderr
    assert "SYNTHETIC" not in result.stderr + result.stdout
