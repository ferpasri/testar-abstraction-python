"""Download published shared cases and record their verified file digests."""

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/specs"


def download(url):
    request = Request(url, headers={"User-Agent": "testar-abstraction-conformance"})
    with urlopen(request, timeout=60) as response:
        content = response.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise ValueError("Download exceeds 16 MiB")
    return content


def prepare():
    releases = json.loads(download("https://api.github.com/repos/ferpasri/testar-abstraction-specs/releases"))
    release = max((item for item in releases if not item["draft"]), key=lambda item: item["published_at"])
    archive = download(release["zipball_url"])
    digest = hashlib.sha256(archive).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        destination = Path(temporary)
        files = {}
        total = 0
        with ZipFile(io.BytesIO(archive)) as bundle:
            for entry in bundle.infolist():
                parts = PurePosixPath(entry.filename).parts
                if entry.is_dir() or len(parts) < 2 or parts[1] != "conformance":
                    continue
                if any(part in (".", "..") or "\\" in part for part in parts):
                    raise ValueError("Unsafe archive path")
                total += entry.file_size
                if total > 64 * 1024 * 1024:
                    raise ValueError("Expanded archive exceeds 64 MiB")
                name = "/".join(parts[1:])
                if name in files:
                    raise ValueError("Duplicate archive path")
                content = bundle.read(entry)
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                files[name] = hashlib.sha256(content).hexdigest()
        manifest = json.loads((destination / "conformance/manifest.json").read_text(encoding="utf-8"))
        compatibility = json.loads((ROOT / "compatibility.json").read_text())
        if any(manifest.get(key) != value for key, value in compatibility.items()):
            raise ValueError("Published conformance behavior is unsupported")
        for suite in manifest["suites"].values():
            for name in suite["cases"]:
                for filename in ("input.json", "rules.json", "expected.json"):
                    json.loads((destination / "conformance" / suite["directory"] / name / filename).read_text(encoding="utf-8"))
        directory = CACHE / digest
        if not directory.exists():
            shutil.copytree(destination, directory)
        selection = {"release": release["tag_name"], "directory": digest,
                     "archive_sha256": digest, "files": files}
        pending = CACHE / "current.tmp"
        pending.write_text(json.dumps(selection, indent=4), encoding="utf-8")
        pending.replace(CACHE / "current.json")
    print("Prepared", release["tag_name"], sum(len(s["cases"]) for s in manifest["suites"].values()), "shared cases")


if __name__ == "__main__":
    prepare()
