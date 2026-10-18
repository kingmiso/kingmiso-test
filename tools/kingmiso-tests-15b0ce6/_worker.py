"""Internal subprocess entry. Suite modes require a matching audited preflight."""
import argparse
import asyncio
import importlib.util
import os
from pathlib import Path
import runpy
import sys
import traceback

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE))


async def run_browser(mode):
    from safety import runtime
    from safety.config import check, write_json
    from playwright.async_api import async_playwright
    job = runtime.require_active()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, chromium_sandbox=True)
        try:
            if mode == 'preflight':
                from safety.preflight import run
                await run(browser)
            else:
                spec = importlib.util.spec_from_file_location('p1_cases', PACKAGE/'timer-regression/cases.py')
                cases = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cases)
                from safety.config import FIXTURE, read_json
                check([name for name,_ in cases.tests(browser)] == read_json(FIXTURE)['p1CaseNames'], 'Unexpected P1 case selection')
                results = []
                for name, fn in cases.tests(browser):
                    cases.ERRORS.clear()
                    try:
                        detail = await fn()
                        detail['checks']['noPageErrors'] = not cases.ERRORS
                        row = {'name':name,'status':'PASS' if all(detail['checks'].values()) else 'FAIL','detail':detail,'pageErrors':cases.ERRORS.copy()}
                    except Exception as error:
                        row = {'name':name,'status':'ERROR','error':str(error),'traceback':traceback.format_exc()[-2000:]}
                    results.append(row)
                    write_json(Path(job['output'])/'p1-results.json', results)
                    print(name + ': ' + row['status'], flush=True)
                    if row['status']!='PASS': break
                check(len(results)==18 and all(r['status']=='PASS' for r in results), 'P1 case failed; expectations unchanged')
        finally:
            await browser.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--mode', choices=('preflight','p1','legacy81'), required=True)
    p.add_argument('--script')
    args = p.parse_args()
    # Explicit imports fail closed if safety code is absent. No sitecustomize,
    # environment switch or historical results directory supplies this guard.
    from safety.config import SUITES, check, validate_job, write_json
    from safety import runtime
    check(sys.flags.optimize == 0, 'Python optimization must not disable original test assertions')
    job = validate_job(args.config, args.mode)
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = job['browsers']
    tag = args.script if args.mode=='legacy81' else args.mode
    if args.mode=='legacy81':
        check(args.script in {s[0] for s in SUITES}, 'Unknown original script')
    runtime.install(job, args.mode)
    try:
        if args.mode=='legacy81':
            sys.path.insert(0, str(PACKAGE/'tests'))
            runpy.run_path(str(PACKAGE/'tests'/args.script), run_name='__main__')
        else:
            asyncio.run(run_browser(args.mode))
    finally:
        write_json(Path(job['output'])/(tag+'-closed.json'), {'pid':os.getpid(),'workerReturned':True})


if __name__=='__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        raise SystemExit(90)
