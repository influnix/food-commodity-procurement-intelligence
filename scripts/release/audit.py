"""Audit an exact release allowlist without touching data or local artifacts."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
DENIED_TOP = {'data', 'artifacts', '.venv', '.git', '__pycache__', '.pytest_cache'}
DENIED_SUFFIX = {'.csv', '.tsv', '.xlsx', '.xls', '.parquet', '.pkl', '.pickle', '.zip', '.gz', '.pyc', '.pem', '.key'}


def release_files(root: Path = ROOT) -> tuple[str, ...]:
    config = tomllib.loads((root / 'configs/release_allowlist.toml').read_text(encoding='utf-8'))
    names = tuple(config['files'])
    if not names or len(names) != len(set(names)):
        raise ValueError('Allowlist must be explicit, unique and nonempty')
    return names


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return (bool(name) and not p.is_absolute() and ':' not in name and '..' not in p.parts and '\\' not in name
            and p.parts[0] not in DENIED_TOP and not any(part.startswith('.') for part in p.parts)
            and p.suffix.lower() not in DENIED_SUFFIX and p.name not in {'.env', 'secrets.json'}) or name in {
                '.gitignore', '.github/workflows/contracts.yml'}


def content_findings(payload: bytes) -> list[str]:
    try:
        text = payload.decode('utf-8')
    except UnicodeDecodeError:
        return ['binary_or_non_utf8']
    patterns = {
        'credential_token': r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})',
        'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'machine_path': r'(?i)(?:[A-Z]:[\\/]Users[\\/]|/(?:Users|home)/[^/\s]+/)',
        'credential_url': r'https?://[^\s/:]+:[^\s/@]+@',
        'literal_secret': r'(?im)\b(?:api_key|access_token|password|client_secret)\s*[:=]\s*[\"\x27][A-Za-z0-9+/=_-]{16,}[\"\x27]',
        'personal_email': r'(?i)\b[A-Z0-9._%+-]+@(?:gmail|hotmail|outlook|naver)\.com\b',
    }
    return [name for name, pattern in patterns.items() if re.search(pattern, text)]


def audit_files(root: Path, names: tuple[str, ...]) -> dict:
    problems = []
    hashes = {}
    total_bytes = 0
    allowed = set(names)
    for name in names:
        if not safe_name(name):
            problems.append({'path': name, 'reason': 'forbidden_path'})
            continue
        p = root / name
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or not p.is_file():
            problems.append({'path': name, 'reason': 'missing_or_symlink'})
            continue
        size = p.stat().st_size
        if size > 256_000:
            problems.append({'path': name, 'reason': 'oversize'})
            continue
        payload = p.read_bytes()
        problems.extend({'path': name, 'reason': reason} for reason in content_findings(payload))
        hashes[name] = hashlib.sha256(payload).hexdigest()
        total_bytes += size
        if p.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', payload.decode('utf-8')):
                if link.startswith(('https://', 'http://', '#', 'mailto:')):
                    continue
                target = (p.parent / link.split('#', 1)[0]).resolve()
                if not target.is_relative_to(root.resolve()) or target.relative_to(root.resolve()).as_posix() not in allowed:
                    problems.append({'path': name, 'reason': 'link_not_in_release', 'target': link})
    return {'passed': not problems, 'files': len(names), 'bytes': total_bytes, 'findings': problems,
            'sha256': hashes, 'scope': 'exact_allowlist_no_source_access',
            'limitation': 'Pattern/content and size checks, not a guarantee of all possible secrets or redistribution rights'}


def tracked_files(root: Path) -> tuple[str, ...]:
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=root, check=True, capture_output=True)
    return tuple(n.decode('utf-8') for n in result.stdout.split(b'\0') if n)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    names = release_files()
    report = audit_files(ROOT, names)
    if args.tracked and set(tracked_files(ROOT)) != set(names):
        report['passed'] = False
        report['findings'].append({'reason': 'tracked_set_must_equal_reviewed_allowlist'})
    print(json.dumps({k: v for k, v in report.items() if k != 'sha256'}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
