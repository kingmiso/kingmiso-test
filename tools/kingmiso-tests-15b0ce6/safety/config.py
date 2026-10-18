"""Portable source identity and run configuration; no game expectations live here."""
import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
FIXTURE = PACKAGE / 'fixtures' / 'source-manifest.json'
ORIGINS = {'http://economy-audit.invalid/', 'http://utc.invalid/', 'http://battle-test.invalid/'}
HEADERS = {'Content-Security-Policy': "connect-src 'self'", 'X-Robots-Tag': 'noindex, nofollow, noarchive'}
SUITES = [('regression.py', 'regression-results.json', 44), ('supplement.py', 'supplement-results.json', 3), ('utc_tests.py', 'utc-results.json', 20), ('battle_browser.py', 'battle-browser-results.json', 14)]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized(raw):
    return raw.replace(b'\r\n', b'\n')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_global_bindings(source):
    import builtins
    import symtable
    table = symtable.symtable(source, '<p1-cases>', 'exec')
    known = {symbol.get_name() for symbol in table.get_symbols() if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()}
    known.update(dir(builtins))
    known.update(('__file__','__name__','__package__'))
    missing = set()
    def visit(scope):
        for symbol in scope.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in known:
                missing.add(symbol.get_name())
        for child in scope.get_children(): visit(child)
    for child in table.get_children(): visit(child)
    check(not missing, 'Unbound P1 module globals: '+', '.join(sorted(missing)))


def validate_source(repo):
    import ast
    fixture = read_json(FIXTURE)
    repo = Path(repo).resolve()
    html = normalized((repo / 'index.html').read_bytes())
    check(digest(html) == fixture['htmlSHA256LF'], 'HTML is not the reviewed P1 source; no tests executed')
    for name, expected in fixture['scenarioSHA256LF'].items():
        check(digest(normalized((PACKAGE / 'tests' / name).read_bytes())) == expected, 'Original scenario changed: ' + name)
    source = (PACKAGE / 'timer-regression' / 'cases.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    check_global_bindings(source)
    state = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='STATE' for t in n.targets))
    check(digest(ast.get_source_segment(source,state).encode('utf-8')) == fixture['p1StateSHA256'], 'P1 state observation changed')
    for name, expected in fixture['p1FunctionSHA256'].items():
        node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
        check(digest(ast.get_source_segment(source, node).encode('utf-8')) == expected, 'P1 assertion/function changed: ' + name)
    return {'htmlSHA256LF': digest(html), 'htmlRawSHA256': digest((repo / 'index.html').read_bytes()), 'scenarioSHA256LF': fixture['scenarioSHA256LF'], 'p1FunctionsUnchanged': True}


def tool_snapshot():
    import os
    files = []
    for folder, dirs, names in os.walk(PACKAGE):
        dirs[:] = [name for name in dirs if name not in ('results', '.venv', '__pycache__', '.git', 'downloads', 'offline-cache')]
        files.extend(Path(folder)/name for name in names if Path(name).suffix in ('.py', '.md', '.txt', '.json'))
    files.sort()
    return {p.relative_to(PACKAGE).as_posix(): digest(normalized(p.read_bytes())) for p in files}


def validate_job(path, mode):
    path = Path(path).resolve()
    job = read_json(path)
    check(mode in ('preflight', 'p1', 'legacy81'), 'Unknown internal worker mode')
    check(Path(job['output']).resolve() == path.parent, 'Job/output mismatch')
    check(Path(job['package']).resolve() == PACKAGE, 'Job/package mismatch')
    check(digest((PACKAGE / 'safety' / 'runtime.py').read_bytes()) == job['guardSHA256'], 'Safety guard changed')
    check(validate_source(job['repo']) == job['source'], 'Run source changed')
    check(tool_snapshot() == job['tools'], 'Tool source changed during run')
    if mode != 'preflight':
        gate = read_json(path.parent / 'safety-gate.json')
        check(gate.get('passed') is True and gate.get('jobSHA256') == digest(path.read_bytes()), 'Successful matching safety gate required')
        check(gate.get('guardSHA256') == job['guardSHA256'], 'Gate/guard mismatch')
        check(all(gate['audit'][key] == 0 for key in ('remoteTCPAttempts', 'dnsWireTransactions', 'udpPayloadWrites', 'violations')), 'Unsafe preflight audit')
    return job
