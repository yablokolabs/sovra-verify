"""The credential audits must detect a real leak, not merely report success.

Two audits exist and both are covered here:

* ``scripts/audit_secrets.py`` is the release gate: it compares against the real
  credential values and refuses forbidden files and archives.
* ``scripts/export_proof.py`` runs a shape-only audit of the working tree as part
  of the evidence bundle.

An audit that always passes is worse than none, so these tests plant a known
value in a temporary tree and require the audit to fail, to name the offending
file, and to never print the value it found. They also pin the shape rule's
entropy guard: a fabricated literal must not be reported as a live credential,
or the audit becomes noise.

No real credential is involved: every value here is fabricated in the test. The
credential file used to drive the comparison lives outside the audited tree on
purpose, so the tests exercise the content check rather than tripping over the
fixture's own file.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import audit_secrets  # noqa: E402
import export_proof  # noqa: E402

#: Fabricated, obviously fake, and long enough to be treated as a credential.
#: Assembled from fragments so this file does not itself contain a key-shaped
#: string: `make audit` scans the repository, and a test that plants a leak must
#: not look like one. The same technique guards the marker list in
#: scripts/check_no_footer.py.
CANARY = "sk-" + "canary-not-a-real-key-" + "0" * 12
HF_SHAPED = "hf_" + "abcdefghijklmnopqrstuvwxyz0123456789"
CANARY_ENV_NAME = "CSCS_INFERENCE_API_KEY"


@pytest.fixture
def audit_env(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A credential file holding the canary, plus the switch that reads it."""
    directory = tmp_path_factory.mktemp("credential-file")
    env_file = directory / "hermes.env"
    env_file.write_text(f"{CANARY_ENV_NAME}={CANARY}\n", encoding="utf-8")
    monkeypatch.setenv("SOVRA_HERMES_ENV", str(env_file))
    monkeypatch.setenv("SOVRA_READ_HERMES_ENV", "1")
    return env_file


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """The audited tree, kept separate from the credential file above."""
    root = tmp_path / "tree"
    root.mkdir()
    return root


def run_audit(root: Path, *extra: str) -> tuple[int, str]:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = audit_secrets.main(["--root", str(root), *extra])
    return code, buffer.getvalue()


def test_a_clean_tree_passes(tree: Path, audit_env: Path) -> None:
    (tree / "docs").mkdir()
    (tree / "docs" / "notes.md").write_text(
        "Nothing secret here: the provider base URL is https://api.inference.cscs.ch/v1\n",
        encoding="utf-8",
    )
    code, output = run_audit(tree)
    assert code == 0, output
    assert "PASS" in output


def test_a_leaked_value_is_detected_and_never_printed(tree: Path, audit_env: Path) -> None:
    (tree / "docs").mkdir()
    (tree / "docs" / "leak.md").write_text(f"provider key: {CANARY}\n", encoding="utf-8")
    code, output = run_audit(tree)
    assert code == 1, output
    assert "FAIL" in output
    assert "docs/leak.md" in output
    # The whole point: the audit reports that it found the value, never the value.
    assert CANARY not in output
    assert "redacted" in output


def test_a_value_in_quotes_is_still_detected(tree: Path, audit_env: Path) -> None:
    (tree / "settings.yaml").write_text(f'api_key: "{CANARY}"\n', encoding="utf-8")
    code, output = run_audit(tree)
    assert code == 1, output
    assert "core slice" in output or "exact value" in output


def test_a_key_shaped_string_is_detected_without_knowing_the_value(
    tree: Path, audit_env: Path
) -> None:
    (tree / "config.json").write_text(
        '{"token": "' + HF_SHAPED + '"}\n', encoding="utf-8"
    )
    code, output = run_audit(tree)
    assert code == 1, output
    assert "key-shaped string" in output


def test_a_dotenv_file_is_refused_but_the_template_is_allowed(tree: Path, audit_env: Path) -> None:
    (tree / ".env").write_text(f"{CANARY_ENV_NAME}={CANARY}\n", encoding="utf-8")
    (tree / ".env.example").write_text(f"{CANARY_ENV_NAME}=\n", encoding="utf-8")
    code, output = run_audit(tree)
    assert code == 1, output
    assert "forbidden file name" in output
    # The documented template is the one file allowed to name a secret variable.
    assert ".env.example:0" not in output


def test_the_credential_file_itself_is_refused(tree: Path, audit_env: Path) -> None:
    (tree / "hermes.env").write_text(f"{CANARY_ENV_NAME}={CANARY}\n", encoding="utf-8")
    code, output = run_audit(tree)
    assert code == 1, output
    assert "forbidden file name" in output
    assert CANARY not in output


def test_a_value_hidden_inside_a_zip_member_is_detected(tree: Path, audit_env: Path) -> None:
    (tree / "exports").mkdir()
    with zipfile.ZipFile(tree / "exports" / "bundle.zip", "w") as archive:
        archive.writestr("report.md", f"key: {CANARY}\n")
        archive.writestr("clean.txt", "nothing to see\n")
    code, output = run_audit(tree)
    assert code == 1, output
    assert "bundle.zip!report.md" in output
    assert CANARY not in output


def test_an_excluded_work_directory_is_not_reported(tree: Path, audit_env: Path) -> None:
    work = tree / ".sovra_work" / "exports"
    work.mkdir(parents=True)
    (work / "analysis.json").write_text(f"key: {CANARY}\n", encoding="utf-8")
    code, output = run_audit(tree)
    assert code == 0, output
    assert "excluded files:    1" in output


def test_a_missing_archive_is_reported(tree: Path, audit_env: Path) -> None:
    (tree / "readme.md").write_text("public\n", encoding="utf-8")
    code, output = run_audit(tree, "--archive", str(tree / "does-not-exist.zip"))
    assert code == 1, output
    assert "was not found" in output


def test_the_manifest_lists_publishable_files_with_reasons(tree: Path, audit_env: Path) -> None:
    (tree / "docs").mkdir()
    (tree / "docs" / "readme.md").write_text("public\n", encoding="utf-8")
    (tree / "SESSION_CONTINUATION.md").write_text("local only\n", encoding="utf-8")
    manifest = tree.parent / "manifest.json"
    code, output = run_audit(tree, "--manifest", str(manifest))
    assert code == 0, output
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["publishable"] == ["docs/readme.md"]
    reasons = {entry["path"]: entry["reason"] for entry in payload["excluded"]}
    assert "SESSION_CONTINUATION.md" in reasons


# ---------------------------------------------------------------------------
# the shape rule used by the evidence bundle's own tree audit
# ---------------------------------------------------------------------------
def test_a_realistic_key_shape_is_treated_as_a_live_credential() -> None:
    realistic = "sk-" + "a1b2c3d4e5f6g7h8i9j0k1l2"
    assert export_proof.looks_like_live_credential(realistic) is True
    # AWS access key ids are AKIA plus sixteen mixed alphanumerics.
    assert export_proof.looks_like_live_credential("AKIA" + "IOSFODNN7EXAMPLE") is True
    # Assembled from fragments, like every other literal in this repository that
    # would otherwise be flagged by the audit it exists to test.
    assert export_proof.looks_like_live_credential(
        "-----BEGIN " + "RSA PRIVATE KEY-----"
    ) is True


def test_a_fabricated_test_literal_is_not_reported() -> None:
    # The literal the provider test uses to prove that masking shortens a value.
    # It is a run of the alphabet: no entropy, and far too short to be a key.
    assert export_proof.looks_like_live_credential("sk-" + "abcdefghijklmnop") is False
    assert export_proof.looks_like_live_credential("hf_" + "abcdefghijklmnopqrstuvwx") is False
