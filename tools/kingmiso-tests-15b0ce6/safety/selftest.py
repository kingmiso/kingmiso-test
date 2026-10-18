"""Offline policy/negative tests. Never launches Chromium or contacts a server."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from .audit import inspect_events
from .config import PACKAGE, digest, validate_job, validate_source
from .runtime import check_context, launch_options, require_active


def log(name, params=None):
    return {'constants':{'logEventTypes':{name:1}},'events':[{'type':1,'phase':1,'params':params or {}}]}


class SafetyTests(unittest.TestCase):
    def test_01_forced_loopback_proxy(self):
        self.assertEqual(launch_options({},1234,'log')['proxy'],{'server':'http://127.0.0.1:1234','bypass':'<-loopback>'})
    def test_02_sandbox_and_headless(self):
        options=launch_options({'headless':False},1,'log')
        self.assertTrue(options['chromium_sandbox'] and options['headless'])
    def test_03_no_security_bypass_flags(self):
        flags=launch_options({},1,'log')['args']
        self.assertFalse(any('--disable-web-security' in f or '--ignore-certificate-errors' in f or '--no-sandbox' in f for f in flags))
    def test_04_dns_and_quic_blocked(self):
        flags=launch_options({},1,'log')['args']
        self.assertIn('--disable-quic',flags)
        self.assertIn('--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',flags)
    def test_05_custom_args_denied(self):
        with self.assertRaises(RuntimeError):launch_options({'args':['--disable-web-security']},1,'log')
    def test_06_custom_executable_denied(self):
        with self.assertRaises(RuntimeError):launch_options({'executable_path':'browser'},1,'log')
    def test_07_custom_profile_channel_denied(self):
        with self.assertRaises(RuntimeError):launch_options({'channel':'chrome'},1,'log')
    def test_08_custom_proxy_denied(self):
        with self.assertRaises(RuntimeError):launch_options({'proxy':{'server':'remote'}},1,'log')
    def test_09_ignore_default_args_denied(self):
        with self.assertRaises(RuntimeError):launch_options({'ignore_default_args':True},1,'log')
    def test_10_disabled_sandbox_denied(self):
        with self.assertRaises(RuntimeError):launch_options({'chromium_sandbox':False},1,'log')
    def test_11_worker_block_required(self):
        with self.assertRaises(RuntimeError):check_context({})
    def test_12_credentials_and_storage_denied(self):
        for key in ('storage_state','client_certificates','http_credentials'):
            with self.subTest(key=key),self.assertRaises(RuntimeError):check_context({'service_workers':'block',key:'external'})
    def test_13_csp_tls_bypass_denied(self):
        for key in ('bypass_csp','ignore_https_errors'):
            with self.subTest(key=key),self.assertRaises(RuntimeError):check_context({'service_workers':'block',key:True})
    def test_14_uninitialized_guard_denied(self):
        with self.assertRaises(RuntimeError):require_active()
    def test_15_remote_tcp_evidence_rejected(self):
        with self.assertRaises(RuntimeError):inspect_events(log('TCP_CONNECT_ATTEMPT',{'address':'203.0.113.1:443'}))
    def test_16_dns_wire_rejected(self):
        with self.assertRaises(RuntimeError):inspect_events(log('DNS_TRANSACTION_QUERY'))
    def test_17_udp_payload_rejected(self):
        with self.assertRaises(RuntimeError):inspect_events(log('UDP_BYTES_SENT'))
    def test_18_local_address_selection_not_payload(self):
        self.assertEqual(inspect_events(log('UDP_CONNECT'))['udpPayloadWrites'],0)
    def test_19_direct_support_import_denied(self):
        code="import sys;sys.path.insert(0,"+repr(str(PACKAGE/'tests'))+");import support"
        result=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('mandatory safety guard',result.stderr)
    def test_20_missing_safety_gate_denied(self):
        from .config import tool_snapshot
        path=PACKAGE/'results'/'nonexistent-selftest'/'job.json'
        job={'package':str(PACKAGE),'output':str(path.parent),'repo':str(PACKAGE.parents[1]),'guardSHA256':digest((PACKAGE/'safety/runtime.py').read_bytes()),'source':{},'tools':{}}
        with patch('safety.config.read_json',side_effect=[job,FileNotFoundError('missing gate')]),patch('safety.config.validate_source',return_value={}),patch('safety.config.tool_snapshot',return_value={}):
            with self.assertRaises(FileNotFoundError):validate_job(path,'p1')
    def test_21_invalid_gate_denied(self):
        path=PACKAGE/'results'/'nonexistent-selftest'/'job.json'
        job={'package':str(PACKAGE),'output':str(path.parent),'repo':str(PACKAGE.parents[1]),'guardSHA256':digest((PACKAGE/'safety/runtime.py').read_bytes()),'source':{},'tools':{}}
        with patch('safety.config.read_json',side_effect=[job,{'passed':False}]),patch('safety.config.validate_source',return_value={}),patch('safety.config.tool_snapshot',return_value={}):
            with self.assertRaises(RuntimeError):validate_job(path,'legacy81')
    def test_22_context_normal_policy(self):
        check_context({'service_workers':'block','bypass_csp':False,'ignore_https_errors':False})
    def test_23_loopback_tcp_allowed(self):
        self.assertEqual(inspect_events(log('TCP_CONNECT_ATTEMPT',{'address':'127.0.0.1:1234'}))['loopbackTCPAttempts'],1)
    def test_24_fixture_is_identity_not_game_answer(self):
        from .config import FIXTURE,read_json
        fixture=read_json(FIXTURE)
        self.assertNotIn('resources',fixture)
        self.assertEqual(len(fixture['p1CaseNames']),18)

    def test_25_unbound_p1_globals_rejected(self):
        from .config import check_global_bindings
        with self.assertRaises(RuntimeError):check_global_bindings('def f(): return MISSING')
        check_global_bindings('import math\ndef f(): return math.pi')
