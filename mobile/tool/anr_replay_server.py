"""Read-only replay of archived synthetic responses for Android ANR diagnosis.

No Agent, database mutation, or model invocation is available on this server.
"""
from __future__ import annotations

import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / '.cache/android_delivery/runtime.json')
    parser.add_argument('--snapshots', type=Path, default=ROOT / 'artifacts/android_delivery_20260908/final_service_readiness_diagnostics')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    fixtures = {key: json.loads((args.snapshots / f'final_{key}_snapshot.json').read_text())
                for key in ('overview', 'runs', 'memories', 'latest_run')}
    records = {item['run_id']: item for item in fixtures['runs']['items']}
    records[fixtures['latest_run']['run_id']] = fixtures['latest_run']

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, body):
            payload = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/readyz':
                return self.respond(200, {'status': 'ready', 'mode': 'read_only_synthetic_replay'})
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + config['access_token']):
                return self.respond(401, {'detail': 'unauthorized'})
            routes = {'/v1/overview': fixtures['overview'], '/v1/runs': fixtures['runs'],
                      '/v1/memories': fixtures['memories']}
            if path in routes:
                return self.respond(200, routes[path])
            if path.startswith('/v1/runs/') and path.rsplit('/', 1)[-1] in records:
                return self.respond(200, records[path.rsplit('/', 1)[-1]])
            self.respond(404, {'detail': 'not in diagnostic fixture'})

        def do_POST(self):
            self.respond(503, {'detail': {'code': 'diagnostic_read_only', 'message': 'Analysis and mutations disabled during ANR diagnosis'}})

    print(f'Read-only synthetic replay on 127.0.0.1:{config["port"]}; all POST requests refused', flush=True)
    ThreadingHTTPServer(('127.0.0.1', config['port']), Handler).serve_forever()


if __name__ == '__main__':
    main()
