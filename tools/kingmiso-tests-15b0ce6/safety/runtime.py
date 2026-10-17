"""Mandatory Playwright guard, including a deny-only proxy below renderer routes.

The proxy never constructs an upstream socket. Chromium receives it before launch.
No environment variable alone enables test imports: install() and an audited gate
are required. This protects this tool's entry points, not arbitrary hostile Python.
"""
import atexit
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socketserver
import threading
import time
from urllib.parse import urlsplit
from .config import HEADERS, ORIGINS, check, normalized, read_json

_active = None
_mode = None
_proxy = None
_lock = threading.Lock()
_proxy_contexts = set()
_original_unroute_all = None


def require_active():
    check(_active is not None, 'Use run_safe.py: mandatory safety guard is not initialized')
    return _active


def safe_url(value):
    parsed = urlsplit(value)
    return parsed.scheme + '://' + (parsed.hostname or '') + parsed.path


def record(event, **data):
    job = require_active()
    path = Path(job['output']) / f'audit-{os.getpid()}.jsonl'
    with _lock:
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'event': event, 'pid': os.getpid(), 'time': time.time(), **data}) + '\n')


def violation(reason):
    record('VIOLATION', reason=reason)
    raise RuntimeError(reason)


class DenyProxy(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(2)
        try:
            line = self.request.recv(8192).split(b'\r\n', 1)[0].decode('ascii', 'replace')
            # No URL query, headers, cookies or bodies enter this audit record.
            parts = line.split(' ')
            record('proxy_denied', method=parts[0], target=parts[1].split('?')[0] if len(parts)>1 else '')
            self.request.sendall(b'HTTP/1.1 502 Blocked by KingMiso safety harness\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        except (OSError, TimeoutError):
            pass


def launch_options(options, proxy_port, netlog):
    check(not any(options.get(k) for k in ('executable_path', 'channel', 'ignore_default_args', 'args', 'proxy', 'env')), 'Custom browser/network settings prohibited')
    check(options.get('chromium_sandbox', True) is not False, 'Chromium sandbox must remain enabled')
    return {**options, 'headless': True, 'chromium_sandbox': True,
            'proxy': {'server': 'http://127.0.0.1:' + str(proxy_port), 'bypass': '<-loopback>'},
            'args': ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', '--disable-background-networking',
                     '--disable-component-update', '--disable-sync', '--disable-quic', '--no-pings',
                     '--force-webrtc-ip-handling-policy=disable_non_proxied_udp', '--log-net-log=' + str(netlog), '--net-log-capture-mode=Default']}


def check_context(options):
    check(options.get('service_workers') == 'block', 'Service Workers must be blocked')
    check(not any(options.get(k) for k in ('storage_state', 'client_certificates', 'http_credentials', 'proxy', 'bypass_csp', 'ignore_https_errors')), 'Credentials, external storage or security bypass prohibited')


def install(job, mode):
    global _active, _mode, _original_unroute_all
    check(_active is None, 'Guard already initialized')
    check(importlib.metadata.version('playwright') == '1.62.0', 'Use the reviewed Playwright 1.62.0 environment; no automatic install')
    _active, _mode = job, mode
    from playwright.async_api import APIRequest, APIRequestContext, Browser, BrowserContext, BrowserType, Route, WebSocketRoute
    import playwright.sync_api as sync_api
    original_launch, original_context, original_close = BrowserType.launch, Browser.new_context, Browser.close
    original_fulfill, original_abort = Route.fulfill, Route.abort
    _original_unroute_all = BrowserContext.unroute_all

    async def prohibited(self, *args, **kwargs):
        violation('Unsafe network/profile/CDP API prohibited')

    def prohibited_sync(self, *args, **kwargs):
        violation('Synchronous or WebSocket upstream API prohibited')

    async def launch(self, **options):
        global _proxy
        check(self.name == 'chromium', 'Only bundled Chromium is reviewed')
        # Validate before even starting the local proxy.
        launch_options(options, 1, 'validation-only')
        check(_proxy is None, 'One browser per audited worker')
        _proxy = socketserver.ThreadingTCPServer(('127.0.0.1', 0), DenyProxy)
        _proxy.daemon_threads = True
        threading.Thread(target=_proxy.serve_forever, daemon=True).start()
        checked = launch_options(options, _proxy.server_address[1], Path(job['output']) / f'netlog-{os.getpid()}.json')
        record('browser_launch', proxy=checked['proxy'], args=checked['args'])
        browser = await original_launch(self, **checked)
        record('browser_started', version=browser.version)
        check(browser.version == '151.0.7922.34', 'Unreviewed Chromium version; stop before any test navigation')
        return browser

    async def new_context(self, **options):
        check_context(options)
        context = await original_context(self, **options)
        check(await context.storage_state() == {'cookies': [], 'origins': []}, 'Context did not start empty')
        record('context_empty', context=id(context), timezone=options.get('timezone_id'))
        async def deny(route):
            await route.abort()
        async def deny_ws(ws):
            record('websocket_denied', url=safe_url(ws.url))
            await ws.close(code=1008, reason='Isolated offline tests')
        await context.route('**/*', deny)
        await context.route_web_socket('**/*', deny_ws)
        def response(value):
            if id(context) in _proxy_contexts and value.url == 'http://proxy-probe.invalid/' and value.status == 502:
                record('proxy_probe_blocked', status=502)
            elif value.url not in ORIGINS:
                record('VIOLATION', reason='Unexpected HTTP response', url=safe_url(value.url))
        context.on('response', response)
        context.on('requestfailed', lambda request: record('request_failed', url=safe_url(request.url), failure=request.failure))
        return context

    async def fulfill(self, **options):
        body = options.get('body', b'')
        raw = body.encode('utf-8') if isinstance(body, str) else body
        actual = hashlib.sha256(normalized(raw)).hexdigest() if raw else ''
        if self.request.url not in ORIGINS or self.request.method != 'GET' or actual != job['source']['htmlSHA256LF'] or options.get('headers', {}).get('Content-Security-Policy') != HEADERS['Content-Security-Policy']:
            violation('Only exact reviewed HTML GET at fake test origins may be fulfilled')
        await original_fulfill(self, **options)
        record('html_fulfilled', url=safe_url(self.request.url), sha256=actual)

    async def abort(self, *args, **kwargs):
        record('route_aborted', url=safe_url(self.request.url), resource=self.request.resource_type, method=self.request.method)
        return await original_abort(self, *args, **kwargs)

    async def close(self, *args, **kwargs):
        result = await original_close(self, *args, **kwargs)
        record('browser_closed')
        return result

    BrowserType.launch, Browser.new_context, Browser.close = launch, new_context, close
    Route.fulfill, Route.abort = fulfill, abort
    for name in ('continue_', 'fetch', 'fallback'):
        setattr(Route, name, prohibited)
    for name in ('launch_persistent_context', 'connect', 'connect_over_cdp'):
        setattr(BrowserType, name, prohibited)
    for name in ('new_cdp_session', 'unroute', 'unroute_all', 'unroute_web_sockets'):
        if hasattr(BrowserContext, name): setattr(BrowserContext, name, prohibited)
    Browser.new_page = prohibited
    Browser.new_browser_cdp_session = prohibited
    APIRequest.new_context = prohibited
    for name in ('fetch', 'get', 'post', 'put', 'delete', 'patch', 'head'):
        setattr(APIRequestContext, name, prohibited)
    WebSocketRoute.connect_to_server = prohibited_sync
    for name in ('launch', 'launch_persistent_context', 'connect', 'connect_over_cdp'):
        setattr(sync_api.BrowserType, name, prohibited_sync)
    record('guard_loaded', mode=mode, guardSHA256=job['guardSHA256'])
    atexit.register(lambda: record('process_exit'))


async def prepare_proxy_probe(context):
    """Preflight-only removal of renderer routes, leaving deny proxy/DNS intact."""
    require_active()
    check(_mode == 'preflight', 'Independent proxy probe is preflight-only')
    _proxy_contexts.add(id(context))
    await _original_unroute_all(context, behavior='wait')
