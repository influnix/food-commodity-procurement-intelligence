"""Offline allowlisted tests; deny checkout data/artifact reads and network."""
from contextlib import ExitStack
import builtins
import io
import json
import os
from pathlib import Path
import socket
import sys
import tomllib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    sys.dont_write_bytecode = True
    # Pytest entry-point autoload can import unrelated globally installed plugins.
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    import pytest
    files = tomllib.loads((ROOT / 'configs/ci.toml').read_text(encoding='utf-8'))['tests']
    protected = tuple((ROOT / name).resolve() for name in ('data', 'artifacts'))
    audit = {'data_or_artifact_opens': 0, 'blocked_attempts': 0, 'network_attempts': 0}

    def guard(original):
        def checked(file, *args, **kwargs):
            if not isinstance(file, int):
                try:
                    path = Path(os.fsdecode(file)).resolve()
                except (TypeError, ValueError):
                    path = None
                if path is not None and any(path.is_relative_to(base) for base in protected):
                    audit['blocked_attempts'] += 1
                    raise PermissionError('CI forbids checkout source and local evidence access')
            return original(file, *args, **kwargs)
        return checked

    def offline(*args, **kwargs):
        audit['network_attempts'] += 1
        raise PermissionError('CI test execution is offline')

    with ExitStack() as stack:
        for module, name in ((builtins, 'open'), (io, 'open'), (os, 'open')):
            stack.enter_context(patch.object(module, name, guard(getattr(module, name))))
        stack.enter_context(patch.object(socket, 'create_connection', offline))
        stack.enter_context(patch.object(socket.socket, 'connect', offline))
        status = int(pytest.main([*files, '-q', '-p', 'no:cacheprovider', '--junitxml=ci-results.junit.xml']))
    print(json.dumps({'ci_scope': 'offline_toy_and_contract', 'exit_code': status, 'access': audit}))
    return status or (1 if audit['blocked_attempts'] or audit['network_attempts'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
