"""Synthetic probes only; no production services, no CSP/TLS bypass."""
import asyncio
from .config import HEADERS, check, write_json
from . import runtime


async def run(browser):
    job = runtime.require_active()
    base = 'http://economy-audit.invalid/'
    checks = {}
    contexts = []
    async def context(product=True):
        ctx = await browser.new_context(service_workers='block')
        contexts.append(ctx)
        if product:
            async def route(r):
                if r.request.url == base and r.request.method == 'GET':
                    from pathlib import Path
                    await r.fulfill(status=200, content_type='text/html', body=(Path(job['repo'])/'index.html').read_bytes(), headers=HEADERS)
                else:
                    await r.abort()
            await ctx.route('**/*', route)
        page = await ctx.new_page()
        response = await page.goto(base if product else 'about:blank', wait_until='load')
        return ctx, page, response
    try:
        a, page, response = await context()
        checks['cspOnActualResponse'] = response.headers.get('content-security-policy') == "connect-src 'self'"
        checks['freshStorage'] = await page.evaluate('localStorage.length===0 && sessionStorage.length===0')
        checks['firebaseUnavailable'] = await page.evaluate("typeof __firebase_config==='undefined' && typeof __initial_auth_token==='undefined' && typeof kmCloudReadyV204==='undefined' && typeof cloudLoadGame==='undefined'")
        checks['cspFetchBlocked'] = await page.evaluate("async()=>{try{await fetch('https://safety-probe.invalid/firebase');return false}catch{return true}}")
        # Fake data only, to check storage isolation/reload; no login or game engine.
        await page.evaluate("currentCustomId='SAFETY_FAKE';kmSaveEnabledV204=true;cloudSaveGame=()=>kmSaveLocalV204();gameState.resources.food=54321;kmLocalWriteV204(currentCustomId);sessionStorage.setItem('probe','fake')")
        await page.reload(wait_until='load')
        checks['fakeSaveReload'] = await page.evaluate("kmLocalReadV204('SAFETY_FAKE').state.resources.food===54321 && sessionStorage.getItem('probe')==='fake'")
        b, page2, _ = await context()
        checks['sameOriginIsolation'] = await page2.evaluate("localStorage.length===0 && sessionStorage.length===0 && kmLocalReadV204('SAFETY_FAKE')===null")
        checks['noIndexedDB'] = await page2.evaluate('async()=>!(await indexedDB.databases()).length')
        checks['noCookies'] = not await a.cookies() and not await b.cookies()
        checks['noServiceWorkers'] = not a.service_workers and not b.service_workers
        # An intrinsic blank page has no product CSP; this exercises routing
        # independently without changing or bypassing the product's actual CSP.
        c, blank, _ = await context(False)
        checks['routeFetchBlocked'] = await blank.evaluate("async()=>{try{await fetch('https://safety-probe.invalid/firestore');return false}catch{return true}}")
        checks['sameOriginWriteBlocked'] = await page2.evaluate("async()=>{try{await fetch('/api/write',{method:'POST',body:'fake'});return false}catch{return true}}")
        checks['imageBlocked'] = await blank.evaluate("()=>new Promise(r=>{const i=new Image();i.onload=()=>r(false);i.onerror=()=>r(true);i.src='https://safety-probe.invalid/probe.png'})")
        checks['websocketBlocked'] = await blank.evaluate("()=>new Promise(r=>{const w=new WebSocket('wss://safety-probe.invalid/ws');w.onopen=()=>r(false);w.onerror=()=>r(true);w.onclose=()=>r(true)})")
        d, proxy_page, _ = await context(False)
        await runtime.prepare_proxy_probe(d)
        blocked = await proxy_page.goto('http://proxy-probe.invalid/', timeout=10000)
        checks['browserHTTPProxyBlocked'] = blocked is not None and blocked.status == 502
        try:
            await proxy_page.goto('https://proxy-probe.invalid/', timeout=10000)
            checks['browserHTTPSProxyBlocked'] = False
        except Exception as error:
            checks['browserHTTPSProxyBlocked'] = 'ERR_TUNNEL_CONNECTION_FAILED' in str(error)
        passed = all(value is True for value in checks.values())
        from pathlib import Path
        write_json(Path(job['output'])/'preflight.json', {'passed':passed,'checks':checks,'browserVersion':browser.version,'contexts':len(contexts)})
        check(passed, 'Preflight failed; no test suite may run')
    finally:
        for ctx in contexts:
            await ctx.close()
