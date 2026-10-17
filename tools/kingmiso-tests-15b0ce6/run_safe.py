"""Portable entry for all browser suites; audited preflight is mandatory."""
import argparse
import datetime
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety.config import PACKAGE, SUITES, check, digest, read_json, tool_snapshot, validate_source, write_json
from safety.audit import inspect_process


def main(argv=None, default_suite='all'):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=PACKAGE.parents[1])
    p.add_argument('--output', type=Path)
    p.add_argument('--browsers', type=Path, help='Existing offline Playwright browser cache; never installed automatically')
    p.add_argument('--suite', choices=('all','p1','legacy81'), default=default_suite)
    p.add_argument('--check', action='store_true', help='Source/import validation only; no browser')
    p.add_argument('--self-test', action='store_true', help='Offline guard unit tests; no browser')
    args = p.parse_args(argv)
    # Validate required versioned code before any child process/browser launch.
    for relative in ('safety/runtime.py','safety/preflight.py','safety/audit.py','fixtures/source-manifest.json','_worker.py'):
        check((PACKAGE/relative).is_file(), 'Required safety source missing: '+relative)
    if args.self_test:
        import unittest
        from safety.selftest import SafetyTests
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SafetyTests))
        return 0 if result.wasSuccessful() else 1
    repo = args.repo.resolve()
    source = validate_source(repo)
    check(importlib.metadata.version('playwright')=='1.62.0', 'Playwright 1.62.0 must already be installed offline')
    from safety import runtime, preflight
    check(callable(runtime.install) and callable(preflight.run), 'Guard import failed')
    if args.check:
        print('STATIC CHECK PASS: '+str(repo)+'; HTML '+source['htmlSHA256LF'])
        return 0
    browser_value = args.browsers or os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    check(bool(browser_value), 'Specify --browsers with an existing offline browser cache')
    browsers = Path(browser_value).resolve()
    check(browsers.is_dir(), 'Browser cache missing; no downloads are performed')
    check(any(browsers.glob('chromium_headless_shell-*')), 'Bundled headless Chromium cache missing')
    check(any(browsers.glob('chromium-*')), 'Bundled Chromium cache missing')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    output = (args.output or PACKAGE/'results'/('portable-'+stamp+'-'+str(os.getpid()))).resolve()
    check(not output.exists(), 'Output must be a new directory; existing results are never overwritten')
    output.mkdir(parents=True, exist_ok=False)
    job = {'schema':1,'repo':str(repo),'package':str(PACKAGE),'output':str(output),'browsers':str(browsers),'source':source,'tools':tool_snapshot(),'guardSHA256':digest((PACKAGE/'safety/runtime.py').read_bytes()),'createdUTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    config = output/'job.json'
    write_json(config, job)
    env = os.environ.copy()
    for name in ('PYTHONPATH','PYTHONHOME','KM_SAFE_RUNTIME','KM_DIAG_ROOT'):
        env.pop(name, None)
    summary = []
    def stage(mode, script=None, expected=None):
        tag = script or mode
        command = [sys.executable,'-I','-B','-u','-X','utf8',str(PACKAGE/'_worker.py'),'--config',str(config),'--mode',mode]
        if script: command += ['--script',script]
        result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        (output/(tag+'.log')).write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        check((output/(tag+'-closed.json')).is_file(), tag+' did not initialize/return safely; inspect log')
        closed = read_json(output/(tag+'-closed.json'))
        audit = inspect_process(output, closed['pid'])
        write_json(output/(tag+'-network.json'), audit)
        print(tag+': exit='+str(result.returncode)+', network=PASS', flush=True)
        check(result.returncode==0, tag+' failed; no automatic rerun or expectation changes. See '+str(output/(tag+'.log')))
        check(expected is None or audit['events'].get('context_empty')==expected, 'Unexpected isolated context count')
        return audit
    try:
        preaudit = stage('preflight', expected=4)
        check(read_json(output/'preflight.json')['passed'], 'Preflight assertions failed')
        check(preaudit['events'].get('proxy_denied',0)>=2 and preaudit['events'].get('websocket_denied',0)>=1, 'Independent proxy/WebSocket blocks not demonstrated')
        write_json(output/'safety-gate.json', {'passed':True,'jobSHA256':digest(config.read_bytes()),'guardSHA256':job['guardSHA256'],'audit':preaudit})
        if args.suite in ('p1','all'):
            stage('p1', expected=18)
            rows = read_json(output/'p1-results.json')
            check(len(rows)==18 and all(r['status']=='PASS' for r in rows), 'P1 results incomplete')
            summary.append({'group':'p1','expected':18,'passed':18,'failed':0,'skipped':0,'notExecuted':0})
        if args.suite in ('legacy81','all'):
            for script, filename, count in SUITES:
                stage('legacy81', script, count)
                rows = read_json(output/filename)
                check(len(rows)==count and all(r['status']=='PASS' for r in rows), 'Original results incomplete: '+script)
                summary.append({'group':script,'expected':count,'passed':count,'failed':0,'skipped':0,'notExecuted':0})
        check(validate_source(repo)==source and tool_snapshot()==job['tools'], 'Source or tools changed during run')
        write_json(output/'summary.json', {'passed':True,'suite':args.suite,'source':source,'groups':summary,'expectedTotal':sum(r['expected'] for r in summary),'passedTotal':sum(r['passed'] for r in summary),'preflightPassed':True,'sourceAndToolsUnchanged':True})
        print('PASS: '+str(output), flush=True)
        return 0
    except BaseException as error:
        write_json(output/'failure.json', {'passed':False,'completedGroups':summary,'error':str(error),'noAutomaticRetry':True})
        raise


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('BLOCKED: '+str(error), file=sys.stderr)
        raise SystemExit(1)
