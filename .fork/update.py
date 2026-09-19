#!/usr/bin/env python3
"""Build an exact upstream release with our patch queue; optionally publish it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / '.fork/config.json').read_text())


def run(*args, cwd=ROOT, env=None):
    try:
        return subprocess.check_output(args, cwd=cwd, text=True, env={**os.environ, **(env or {})}).strip()
    except subprocess.CalledProcessError as error:
        if error.output:
            print(error.output, file=sys.stderr)
        raise


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(upstream, output):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Build on macOS ARM64 (studio, m1, or a macos-15 Actions runner).')
    if upstream == 'latest':
        upstream = json.loads(run('gh', 'api', f"repos/{CONFIG['upstream_repository']}/releases/latest"))['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+', upstream):
        raise ValueError('Expected an exact stable upstream tag such as v7.2.157.')
    revision = CONFIG['patch_revision']
    if type(revision) is not int or revision < 1:
        raise ValueError('patch_revision must be a positive integer')
    patches = sorted((ROOT / '.fork/patches').glob('*.patch'))
    if not patches:
        raise ValueError('Refusing to build an unpatched release: patch queue is empty.')
    source_commit = run('git', 'rev-parse', 'HEAD')
    dirty = bool(run('git', 'status', '--porcelain'))
    version = f'{upstream[1:]}+mj.{revision}'
    tag = f'mj-{upstream}.{revision}'
    if output.exists() and any(output.iterdir()):
        raise ValueError(f'Output directory must be empty: {output}')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cliproxy-build-') as temporary:
        source = Path(temporary)
        run('git', 'init', '-q', str(source))
        run('git', 'fetch', '--quiet', '--no-tags', '--depth=1',
            f"https://github.com/{CONFIG['upstream_repository']}.git", f'refs/tags/{upstream}', cwd=source)
        run('git', 'checkout', '--quiet', '--detach', 'FETCH_HEAD', cwd=source)
        upstream_commit = run('git', 'rev-parse', 'HEAD', cwd=source)
        for patch in patches:
            # No fuzzy application, conflict resolution, or silent patch skipping.
            run('git', 'apply', '--index', str(patch), cwd=source)
        print(f'Testing {upstream} with patch revision {revision}', flush=True)
        run('go', 'test', './internal/runtime/executor/...', './internal/translator/...', cwd=source)
        binary = source / 'cliproxyapi'
        date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        run('go', 'build', '-trimpath',
            f'-ldflags=-s -w -X main.Version={version} -X main.Commit={source_commit} -X main.BuildDate={date}',
            '-o', str(binary), './cmd/server', cwd=source, env={'CGO_ENABLED':'1'})
        asset = f'cliproxyapi-{version}-{revision}-arm64.zip'
        archive = output / asset
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(binary, 'cliproxyapi')
            bundle.write(source / 'LICENSE', 'LICENSE')
        binary_sha256 = sha(binary)
        # The homeserver is x86-64 Linux. Keep the identical tested patch queue.
        linux_binary = source / 'cliproxyapi-linux-amd64'
        run('go', 'build', '-trimpath',
            f'-ldflags=-s -w -X main.Version={version} -X main.Commit={source_commit} -X main.BuildDate={date}',
            '-o', str(linux_binary), './cmd/server', cwd=source,
            env={'GOOS': 'linux', 'GOARCH': 'amd64', 'CGO_ENABLED': '0'})
        linux_archive = output / f'cliproxyapi-{version}-{revision}-linux-amd64.zip'
        with zipfile.ZipFile(linux_archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(linux_binary, 'cliproxyapi')
            bundle.write(source / 'LICENSE', 'LICENSE')
        linux_sha256 = sha(linux_binary)
    descriptor = {
        'version': version, 'build': str(revision), 'arch': 'arm64',
        'asset': asset, 'sha256': sha(archive), 'binary_sha256': binary_sha256, 'repository': CONFIG['repository'],
        'release_tag': tag, 'source_commit': source_commit, 'dirty': dirty,
        'upstream_tag': upstream, 'upstream_commit': upstream_commit,
        'patches': {p.name: sha(p) for p in patches},
    }
    (output / 'release.json').write_text(json.dumps(descriptor, indent=2) + '\n')
    linux_descriptor = descriptor | {
        'os': 'linux', 'arch': 'amd64', 'asset': linux_archive.name,
        'sha256': sha(linux_archive), 'binary_sha256': linux_sha256,
    }
    (output / 'release-linux-amd64.json').write_text(json.dumps(linux_descriptor, indent=2) + '\n')
    print(json.dumps(descriptor, indent=2))
    return descriptor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default=CONFIG['upstream_tag'], help='Exact tag, or latest')
    parser.add_argument('--output', type=Path, required=True, help='Empty output directory')
    parser.add_argument('--publish', action='store_true', help='Publish a validated build; never deploy it')
    args = parser.parse_args()
    if args.publish and run('git', 'status', '--porcelain'):
        raise ValueError('Commit the patch and workflow before publishing; local builds can use uncommitted edits.')
    if args.publish:
        # An existing release is immutable. Scheduled runs do nothing for the same version.
        upstream = args.upstream
        if upstream == 'latest':
            upstream = json.loads(run('gh', 'api', f"repos/{CONFIG['upstream_repository']}/releases/latest"))['tag_name']
        args.upstream = upstream
        tag = f"mj-{upstream}.{CONFIG['patch_revision']}"
        releases = json.loads(run('gh', 'api', f"repos/{CONFIG['repository']}/releases?per_page=100"))
        if any(r['tag_name'] == tag for r in releases):
            print(f'{tag} already exists; bump patch_revision when changing the patch or build recipe.')
            return
    output = args.output.resolve()
    descriptor = build(args.upstream, output)
    if args.publish:
        if run('git', 'status', '--porcelain') or run('git', 'rev-parse', 'HEAD') != descriptor['source_commit']:
            raise ValueError('Fork changed during build; refusing to publish.')
        notes = output / 'notes.md'
        notes.write_text(f"Upstream {descriptor['upstream_tag']} ({descriptor['upstream_commit']}).\n\n"
                         f"Fork source {descriptor['source_commit']}; patch revision {descriptor['build']}.\n\n"
                         'Executor and translator tests passed. macOS ARM64 and Linux AMD64 builds. Deployment to the central LXC is a separate operation.\n')
        # Upload as draft, then expose only when all platform archives and descriptors are present.
        run('gh', 'release', 'create', descriptor['release_tag'], str(output / descriptor['asset']),
            str(output / 'release.json'), str(output / 'release-linux-amd64.json'),
            str(output / json.loads((output / 'release-linux-amd64.json').read_text())['asset']), '--repo', CONFIG['repository'], '--target', descriptor['source_commit'],
            '--title', descriptor['version'], '--notes-file', str(notes), '--draft')
        run('gh', 'release', 'edit', descriptor['release_tag'], '--repo', CONFIG['repository'], '--draft=false', '--latest')


if __name__ == '__main__':
    main()
