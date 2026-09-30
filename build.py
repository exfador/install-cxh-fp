import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOOTSTRAP = ROOT / "bootstrap"
ENCODING = "utf-8"
SETTINGS = (
    ("ManifestSettings", "manifest_settings.py"),
    ("ArchiveSettings", "archive_settings.py"),
)
SOURCES = (
    ("manifest.py", "ManifestSettings"),
    ("archive.py", "ArchiveSettings"),
    ("verify.py", None),
)


def constants_source():
    sections = []
    for name, filename in SETTINGS:
        content = (BOOTSTRAP / filename).read_text(encoding=ENCODING)
        sections.append(
            f"class {name}:\n"
            + "\n".join("    " + line for line in content.splitlines())
        )
    return "\n\n".join(sections)


def verifier_source():
    sections = [constants_source()]
    for filename, namespace in SOURCES:
        content = (BOOTSTRAP / filename).read_text(encoding=ENCODING)
        lines = [
            line
            for line in content.splitlines()
            if not line.startswith("from bootstrap")
        ]
        sections.append("\n".join(lines).replace("settings.", f"{namespace}."))
    return "\n\n".join(sections) + "\n"


def main():
    source = verifier_source()
    compile(source, "embedded-verifier.py", "exec")
    template = (ROOT / "installer.sh.in").read_text(encoding=ENCODING)
    service = (ROOT / "cxh-fp.service").read_bytes()
    result = template.replace(
        "__EMBEDDED_VERIFIER_BASE64__",
        base64.b64encode(source.encode(ENCODING)).decode("ascii"),
    )
    result = result.replace(
        "__EMBEDDED_SERVICE_BASE64__", base64.b64encode(service).decode("ascii")
    )
    destination = ROOT / "install_cxh_fp.sh"
    destination.write_text(result, encoding=ENCODING)
    destination.chmod(0o755)


if __name__ == "__main__":
    main()
