import argparse
import hashlib
import json
from pathlib import Path

from bootstrap.archive import extract_release
from bootstrap.manifest import ManifestError, parse_envelope, verify_envelope

PUBLIC_KEYS = (
    "dda382fc2feabdd8198fd1dac0b3395b12198a44c19f39df96af183f0fe791a7",
    "bf11e13ee0b888aafa65a04beb35eed373aba1c11c7a84a721e3582d58e5ee02",
)
REPOSITORY = "exfador/cxh-fp"
MINIMUM_VERSION = "1.0"
MANIFEST_LIMIT = 256 * 1024
READ_BYTES = 1024 * 1024
REQUIRED_FILES = frozenset(
    {"main.py", "setup.py", "first_setup.py", "requirements.txt"}
)


def signed_manifest(envelope):
    failure = ManifestError("Release signature is not trusted")
    for key in PUBLIC_KEYS:
        try:
            return verify_envelope(envelope, key, REPOSITORY, MINIMUM_VERSION)
        except ManifestError as error:
            failure = error
    raise failure


def verified_manifest(path):
    if path.is_symlink() or path.stat().st_size > MANIFEST_LIMIT:
        raise ValueError("Invalid manifest file")
    manifest = signed_manifest(parse_envelope(path.read_bytes()))
    if not REQUIRED_FILES.issubset(manifest["files"]):
        raise ValueError("Release is incomplete")
    return manifest


def verify_archive(path, manifest):
    if path.is_symlink() or path.stat().st_size != manifest["archive_size"]:
        raise ValueError("Archive size mismatch")
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(READ_BYTES):
            checksum.update(chunk)
    if checksum.hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Archive checksum mismatch")


def prepare_release(manifest_path, archive_path, destination):
    manifest = verified_manifest(manifest_path)
    verify_archive(archive_path, manifest)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists")
    destination.mkdir(mode=0o700)
    extract_release(archive_path, destination, manifest["files"])
    return manifest["version"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    try:
        version = prepare_release(
            arguments.manifest, arguments.archive, arguments.destination
        )
    except (ValueError, OSError, json.JSONDecodeError):
        parser.exit(1, "Release verification failed; installation stopped.\n")
    print(version)


if __name__ == "__main__":
    main()
