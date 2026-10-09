"""Build verified full/hotfix resources from immutable Git trees.

resource-manifest.json travels inside each ZIP. mah_res-manifest.json is produced
after archiving and describes those ZIPs, including their size and SHA-256.
Content IDs hash UTF-8 rows: path<TAB>size<TAB>sha256<LF>, sorted by UTF-16 path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOTS = ("image", "index", "model", "pipeline", "announcement")
MANIFEST = "resource-manifest.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_path(path: str):
    if (not path or path.split('/')[0] not in ROOTS or '\\' in path or ':' in path
            or any(ord(c) < 32 for c in path) or any(p in ('', '.', '..') for p in path.split('/'))):
        raise ValueError(f"Invalid resource path: {path}")


def inventory(files: dict[str, bytes]) -> dict:
    for name in files:
        validate_path(name)
    return {name: {"size": len(data), "sha256": sha(data)} for name, data in sorted(files.items())}


def content_id(files: dict) -> str:
    rows = ''.join(f"{name}\t{files[name]['size']}\t{files[name]['sha256']}\n"
                   for name in sorted(files, key=lambda s: s.encode('utf-16-be')))
    return sha(rows.encode('utf-8'))


def git_files(repo: Path, ref: str) -> dict[str, bytes]:
    commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', '--verify', ref + '^{commit}'], text=True).strip()
    process = subprocess.Popen(['git', '-C', str(repo), 'archive', commit], stdout=subprocess.PIPE)
    result = {}
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                if member.name.split('/')[0] not in ROOTS or member.isdir():
                    continue
                validate_path(member.name)
                if not member.isfile():
                    raise ValueError(f"Resource must be a regular file: {member.name}")
                result[member.name] = archive.extractfile(member).read()
        if process.wait() != 0:
            raise ValueError('Cannot read resource Git tree')
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    return result


def build(output: Path, version: str, target: dict[str, bytes], base_version: str = '', base: dict[str, bytes] | None = None):
    if not version or any(ord(c) < 32 for c in version):
        raise ValueError('Invalid version')
    files = inventory(target)
    for name in ('ui', 'characters', 'ar'):
        if not isinstance(json.loads(target[f'index/{name}.json']), (dict, list)):
            raise ValueError(f'Invalid {name} index')
    for prefix in ('image/character/', 'image/ar/'):
        if not any(name.startswith(prefix) for name in target):
            raise ValueError(f'Missing {prefix}')
    output.mkdir(parents=True, exist_ok=True)
    safe_version = re.sub(r'[/\\:*?"<>|]', '_', version)
    common = {"format": 1, "version": version, "contentId": content_id(files), "files": files}
    packages = []

    def package(kind, changed, deleted, base_version='', base_id=''):
        manifest = dict(common, kind=kind, baseVersion=base_version, baseContentId=base_id,
                        changed=sorted(changed), deleted=sorted(deleted))
        name = f'mah_res-{kind}-{safe_version}.zip'
        path = output / name
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, separators=(',', ':')))
            for entry in sorted(changed):
                archive.writestr(entry, target[entry])
        packages.append({"name": name, "size": path.stat().st_size,
                         "sha256": sha(path.read_bytes()), "manifest": manifest})

    package('full', target.keys(), [])
    if base is not None:
        if not base_version:
            raise ValueError('A hotfix needs a named baseline')
        before = inventory(base)
        package('hotfix', [p for p in files if before.get(p) != files[p]], before.keys() - files.keys(),
                base_version, content_id(before))
    else:
        # Keep the historical hotfix asset for older consumers, explicitly mark it full.
        full = output / packages[0]['name']
        alias = output / f'mah_res-hotfix-{safe_version}.zip'
        alias.write_bytes(full.read_bytes())
    descriptor = {"format": 1, "version": version, "contentId": common['contentId'], "packages": packages}
    (output / 'mah_res-manifest.json').write_text(json.dumps(descriptor, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return descriptor


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('dist'))
    parser.add_argument('--version', required=True)
    parser.add_argument('--target', default='HEAD')
    parser.add_argument('--base', default='')
    args = parser.parse_args()
    # An explicitly supplied but invalid base must fail, not silently produce a false delta.
    build(args.output, args.version, git_files(args.repo, args.target), args.base,
          git_files(args.repo, args.base) if args.base else None)
