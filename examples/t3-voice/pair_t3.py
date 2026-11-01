"""Mint a 30-day full-access MCP client token for the running T3 Code server.

Uses T3's own pairing-code OAuth flow, the same path an outside agent takes.
Run once; the token lands in t3-voice-token.txt next to this script.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
REDIRECT = 'http://127.0.0.1/maeve'


def cli(*args):
    program = Path.home() / 'AppData/Local/Programs/t3code'
    env = dict(os.environ, ELECTRON_RUN_AS_NODE='1', T3CODE_DESKTOP_CLI_LAUNCHER='1')
    result = subprocess.run([str(program / 'T3 Code (Beta).exe'),
                             str(program / 'resources/server.asar/apps/server/dist/bin.mjs'), *args],
                            capture_output=True, text=True, encoding='utf-8', env=env, timeout=60)
    if result.returncode:
        raise SystemExit('T3 CLI failed: ' + result.stderr.strip()[-300:])
    return result.stdout


def post(origin, path, body, form=False):
    data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
    request = urllib.request.Request(origin + path, data, {
        'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json',
        'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode('utf-8') or 'null')
    except urllib.error.HTTPError as error:
        raise SystemExit(path + ' failed: ' + error.read().decode('utf-8', 'replace')[:300])


def main():
    runtime = json.loads((Path.home() / '.t3/userdata/server-runtime.json').read_text('utf-8'))
    origin = runtime['origin']
    code = json.loads(cli('auth', 'pairing', 'create', '--ttl', '10m', '--label', 'Maeve voice pairing', '--json'))['credential']
    client = post(origin, '/oauth/mcp/register', {'client_name': 'Maeve voice panel', 'redirect_uris': [REDIRECT],
                                                  'token_endpoint_auth_method': 'none'})
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    authorization = {'response_type': 'code', 'client_id': client['client_id'], 'redirect_uri': REDIRECT,
                     'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': 'maeve',
                     'resource': origin + '/mcp'}
    decision = post(origin, '/oauth/mcp/decision', {'authorization': authorization,
                    'decision': {'_tag': 'pairing-code', 'access': 'full-access', 'code': code}})
    grant = urllib.parse.parse_qs(urllib.parse.urlparse(decision['redirectTo']).query)['code'][0]
    token = post(origin, '/oauth/mcp/token', {'grant_type': 'authorization_code', 'code': grant,
                 'redirect_uri': REDIRECT, 'client_id': client['client_id'], 'code_verifier': verifier,
                 'resource': origin + '/mcp'}, form=True)
    (ROOT / 't3-voice-token.txt').write_text(token['access_token'], 'utf-8')
    print('Token saved to t3-voice-token.txt; expires in %d days.' % (token['expires_in'] // 86400))


if __name__ == '__main__':
    main()
