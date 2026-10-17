"""Fail closed if Chromium NetLog evidence is missing, incomplete or unsafe."""
import collections
from pathlib import Path
from .config import check, read_json


def inspect_events(log):
    names = {v: k for k, v in log['constants']['logEventTypes'].items()}
    tcp = udp = 0
    for event in log['events']:
        name, params = names[event['type']], event.get('params', {})
        if name == 'TCP_CONNECT_ATTEMPT' and event['phase'] == 1:
            check(params.get('address', '').startswith('127.0.0.1:'), 'Remote TCP attempt')
            tcp += 1
        if name == 'TCP_CONNECT' and params.get('remote_address'):
            check(params['remote_address'].startswith('127.0.0.1:'), 'Remote TCP connection')
        check(name not in ('UDP_BYTES_SENT', 'DNS_TRANSACTION_QUERY', 'DNS_TRANSACTION_ATTEMPT', 'DNS_TRANSACTION_HTTPS_ATTEMPT'), 'External DNS/UDP event: ' + name)
        if name == 'UDP_CONNECT' and event['phase'] == 1:
            udp += 1
    return {'loopbackTCPAttempts': tcp, 'udpLocalAddressSelections': udp, 'remoteTCPAttempts': 0, 'dnsWireTransactions': 0, 'udpPayloadWrites': 0}


def inspect_process(output, pid, expected_contexts=None):
    import json
    output = Path(output)
    rows = [json.loads(line) for line in (output / f'audit-{pid}.jsonl').read_text(encoding='utf-8').splitlines()]
    counts = collections.Counter(row['event'] for row in rows)
    check(counts['VIOLATION'] == 0, 'Safety guard violation')
    check(counts['guard_loaded'] == counts['browser_started'] == counts['browser_closed'] == counts['process_exit'] == 1, 'Incomplete browser lifecycle evidence')
    if expected_contexts is not None:
        check(counts['context_empty'] == expected_contexts, 'Unexpected isolated context count')
    return {'passed': True, 'pid': pid, 'events': dict(counts), 'violations': 0, **inspect_events(read_json(output / f'netlog-{pid}.json'))}
