import base64
import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bootstrap import verify
from bootstrap.manifest import canonical_manifest

REQUIRED_SOURCE = {
    "main.py": b"print('ready')\n",
    "setup.py": b"pass\n",
    "first_setup.py": b"pass\n",
    "requirements.txt": b"--require-hashes\n",
}


@pytest.fixture
def signing_key(monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    monkeypatch.setattr(verify, "PUBLIC_KEY", public.hex())
    return key


def signed_release(tmp_path, key, sources=None, modes=None):
    sources = REQUIRED_SOURCE if sources is None else sources
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in sources.items():
            item = zipfile.ZipInfo(name)
            item.external_attr = (modes or {}).get(name, stat.S_IFREG | 0o600) << 16
            target.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)
    manifest = {
        "version": "1.1",
        "repository": verify.REPOSITORY,
        "archive_size": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in sources.items()
        },
    }
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest, key)
    return path, archive, tmp_path / "destination"


def write_manifest(path, manifest, key):
    envelope = {
        "manifest": manifest,
        "signature": base64.b64encode(key.sign(canonical_manifest(manifest))).decode(
            "ascii"
        ),
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")


def test_verified_release_extracts_exact_bytes(tmp_path, signing_key):
    manifest, archive, destination = signed_release(tmp_path, signing_key)
    assert verify.prepare_release(manifest, archive, destination) == "1.1"
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == REQUIRED_SOURCE


@pytest.mark.parametrize(
    "mutation",
    [
        "archive",
        "signature",
        "repository",
        "downgrade",
        "unknown",
        "digest",
        "size",
        "key",
    ],
)
def test_tampering_stops_before_extraction(
    tmp_path, signing_key, mutation, monkeypatch
):
    manifest, archive, destination = signed_release(tmp_path, signing_key)
    envelope = json.loads(manifest.read_text(encoding="utf-8"))
    apply_mutation(mutation, envelope, archive, signing_key, monkeypatch)
    manifest.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError):
        verify.prepare_release(manifest, archive, destination)
    assert not destination.exists()


def apply_mutation(mutation, envelope, archive, key, monkeypatch):
    operations = {
        "archive": lambda: archive.write_bytes(archive.read_bytes() + b"changed"),
        "signature": lambda: envelope.update(
            signature=base64.b64encode(b"x" * 64).decode("ascii")
        ),
        "repository": lambda: envelope["manifest"].update(
            repository="attacker/project"
        ),
        "downgrade": lambda: envelope["manifest"].update(version="1.0"),
        "unknown": lambda: envelope["manifest"].update(extra=True),
        "digest": lambda: envelope["manifest"].update(archive_sha256="0" * 64),
        "size": lambda: envelope["manifest"].update(archive_size=True),
        "key": lambda: monkeypatch.setattr(verify, "PUBLIC_KEY", "01" * 32),
    }
    operations[mutation]()
    if mutation not in {"archive", "signature", "key"}:
        envelope["signature"] = base64.b64encode(
            key.sign(canonical_manifest(envelope["manifest"]))
        ).decode("ascii")


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/tmp/escape.py",
        "app/../../escape.py",
        "plugins/evil.py",
        "configs/_main.cfg",
        "app/file.key",
        "app/file.pyc",
        "app\\escape.py",
        "app/CON.py",
        "app/.env",
        "app/FILE.py/../file.py",
    ],
)
def test_even_signed_unsafe_paths_are_rejected(tmp_path, signing_key, path):
    sources = {**REQUIRED_SOURCE, path: b"pass\n"}
    manifest, archive, destination = signed_release(tmp_path, signing_key, sources)
    with pytest.raises(ValueError):
        verify.prepare_release(manifest, archive, destination)
    assert not (tmp_path / "escape.py").exists()


def test_symlink_entry_is_rejected(tmp_path, signing_key):
    sources = {**REQUIRED_SOURCE, "app/link.py": b"../../outside"}
    manifest, archive, destination = signed_release(
        tmp_path, signing_key, sources, {"app/link.py": stat.S_IFLNK | 0o777}
    )
    with pytest.raises(ValueError):
        verify.prepare_release(manifest, archive, destination)
    assert not (destination / "main.py").exists()


@pytest.mark.parametrize(
    "data",
    [
        b'{"manifest":{},"manifest":{},"signature":""}',
        b"[",
        b"x" * (verify.MANIFEST_LIMIT + 1),
        b"\xff",
    ],
)
def test_invalid_json_is_rejected(tmp_path, signing_key, data):
    manifest, archive, destination = signed_release(tmp_path, signing_key)
    manifest.write_bytes(data)
    with pytest.raises(ValueError):
        verify.prepare_release(manifest, archive, destination)
    assert not destination.exists()


def test_existing_destination_and_private_data_are_preserved(tmp_path, signing_key):
    manifest, archive, destination = signed_release(tmp_path, signing_key)
    destination.mkdir()
    marker = destination / "private.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError):
        verify.prepare_release(manifest, archive, destination)
    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "sources",
    [
        {"main.py": b"pass\n"},
        {**REQUIRED_SOURCE, "app/FILE.py": b"pass\n", "app/file.py": b"pass\n"},
        {**REQUIRED_SOURCE, "app/huge.txt": b"a" * 1_000_000},
    ],
)
def test_incomplete_colliding_and_bomb_releases_fail(
    tmp_path, signing_key, sources
):
    manifest, archive, destination = signed_release(tmp_path, signing_key, sources)
    with pytest.raises((ValueError, SyntaxError)):
        verify.prepare_release(manifest, archive, destination)


def test_each_file_digest_is_verified(tmp_path, signing_key):
    manifest, archive, destination = signed_release(tmp_path, signing_key)
    envelope = json.loads(manifest.read_text(encoding="utf-8"))
    envelope["manifest"]["files"]["main.py"] = "0" * 64
    write_manifest(manifest, envelope["manifest"], signing_key)
    with pytest.raises(ValueError):
        verify.prepare_release(manifest, archive, destination)


def test_signed_project_uses_newer_syntax_than_bootstrap(tmp_path, signing_key):
    sources = dict(REQUIRED_SOURCE)
    sources["main.py"] = b"match value:\n    case 1:\n        pass\n"
    manifest, archive, destination = signed_release(tmp_path, signing_key, sources)
    assert verify.prepare_release(manifest, archive, destination) == "1.1"
    assert (destination / "main.py").read_bytes() == sources["main.py"]


def test_signed_directory_entry_works_on_system_python(tmp_path, signing_key):
    sources = dict(REQUIRED_SOURCE)
    sources["app/module.py"] = b"pass\n"
    manifest, archive, destination = signed_release(tmp_path, signing_key, sources)
    with zipfile.ZipFile(archive, "a") as target:
        target.writestr("app/", b"")
    envelope = json.loads(manifest.read_text(encoding="utf-8"))["manifest"]
    envelope["archive_size"] = archive.stat().st_size
    envelope["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    write_manifest(manifest, envelope, signing_key)
    assert verify.prepare_release(manifest, archive, destination) == "1.1"
    assert (destination / "app/module.py").read_bytes() == b"pass\n"
