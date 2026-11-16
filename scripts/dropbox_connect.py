#!/usr/bin/env python3
"""Link the Dropbox account to the photo catalog, once. The app key, the app secret and the
refresh token the consent gives go into Google Secret Manager (config.DropboxLink) and
nowhere else: not on disk, not on a command line, not on the screen.

    py -3 scripts\\dropbox_connect.py            the consent in the browser, then the secrets written
    py -3 scripts\\dropbox_connect.py --check    the secrets read back and Dropbox asked who we are

Needs the gcloud CLI signed in (fennec-it, General tab, GCS Sign In) and the Secret Manager
API on. Standard library only. The steps are in docs/dropbox_gcp_albums_plan_*.docx."""
import argparse
import base64
import getpass
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fennec_images.config import DropboxLink as _DL


class LinkError(RuntimeError):
    """Something the user has to act on; the message says what."""


def gcloud(args: list, data: bytes | None = None) -> subprocess.CompletedProcess:
    exe = shutil.which(_DL.GCLOUD)
    if not exe:
        raise LinkError('the gcloud CLI was not found -- install the Google Cloud CLI')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.run([exe] + args + ['--quiet'], input=data, capture_output=True,
                          timeout=_DL.TIMEOUT_S, creationflags=flags)


def _said(r: subprocess.CompletedProcess) -> str:
    # gcloud's own first words; the rest is the same thing said three more times
    return (r.stderr or b'').decode('utf-8', 'replace').strip()[:300]


def gcp_project(given: str) -> str:
    if given:
        return given
    r = gcloud(['config', 'get-value', 'project'])
    value = (r.stdout or b'').decode().strip()
    if r.returncode != 0 or value in ('', '(unset)'):
        raise LinkError('no GCP project -- pass --project, or run: gcloud config set project <id>')
    return value


def secrets_ready(project: str) -> None:
    r = gcloud(['secrets', 'list', '--limit', '1', '--project', project])
    if r.returncode != 0:
        raise LinkError('Secret Manager is not reachable in project %s. Sign in (gcloud auth '
                        'login) and run:\n  gcloud services enable secretmanager.googleapis.com '
                        '--project %s\n%s' % (project, project, _said(r)))


def secret_put(project: str, name: str, value: str) -> None:
    if gcloud(['secrets', 'describe', name, '--project', project]).returncode != 0:
        r = gcloud(['secrets', 'create', name, '--replication-policy', 'automatic',
                    '--project', project])
        if r.returncode != 0:
            raise LinkError('could not create the secret %s\n%s' % (name, _said(r)))
    # the value travels on stdin: never an argument, never a file
    r = gcloud(['secrets', 'versions', 'add', name, '--data-file=-', '--project', project],
               data=value.encode('utf-8'))
    if r.returncode != 0:
        raise LinkError('could not write the secret %s\n%s' % (name, _said(r)))


def secret_get(project: str, name: str) -> str:
    r = gcloud(['secrets', 'versions', 'access', 'latest', '--secret', name, '--project', project])
    if r.returncode != 0:
        raise LinkError('could not read the secret %s -- run this script without --check first\n%s'
                        % (name, _said(r)))
    return (r.stdout or b'').decode('utf-8').strip()


def _http(req: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=_DL.TIMEOUT_S) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')[:300]
        raise LinkError('Dropbox answered %s: %s' % (exc.code, body)) from None
    except urllib.error.URLError as exc:
        raise LinkError('Dropbox was not reached: %s' % exc.reason) from None


def token_call(app_key: str, app_secret: str, fields: dict) -> dict:
    basic = base64.b64encode(('%s:%s' % (app_key, app_secret)).encode()).decode()
    req = urllib.request.Request(_DL.URL_TOKEN, data=urllib.parse.urlencode(fields).encode(),
                                 headers={'Authorization': 'Basic ' + basic})
    return _http(req)


def api_call(access_token: str, route: str, arg) -> dict:
    req = urllib.request.Request(_DL.URL_API + route, data=json.dumps(arg).encode(),
                                 headers={'Authorization': 'Bearer ' + access_token,
                                          'Content-Type': 'application/json'})
    return _http(req)


def check_scopes(scope: str) -> None:
    have = scope.split()
    missing = [s for s in _DL.SCOPES_NEEDED if s not in have]
    if missing:
        raise LinkError('the Dropbox app lacks the permission(s) %s -- tick them on the app\'s '
                        'Permissions tab, press Submit, and run this again' % ', '.join(missing))
    writes = [s for s in have if _DL.SCOPE_WRITE_MARK in s]
    if writes:
        print('[WARN] the app may also change files (%s). The catalog only reads: untick these '
              'on the Permissions tab and run this again.' % ', '.join(writes))


def report(access_token: str) -> None:
    who = api_call(access_token, 'users/get_current_account', None)
    space = api_call(access_token, 'users/get_space_usage', None)
    top = api_call(access_token, 'files/list_folder', {'path': '', 'limit': 2000})
    used = space.get('used', 0) / 1e9
    total = (space.get('allocation') or {}).get('allocated', 0) / 1e9
    folders = sorted(e['name'] for e in top.get('entries', []) if e.get('.tag') == 'folder')
    print('[OK] Dropbox account: %s (%s)' % (who['name']['display_name'], who.get('email', '')))
    print('[OK] space used: %.0f GB of %.0f GB' % (used, total))
    print('[OK] %d top folder(s)%s: %s' % (len(folders), ', more to list' if top.get('has_more') else '',
                                           ', '.join(folders)))


def connect(project: str) -> bool:
    secrets_ready(project)
    app_key = input('App key: ').strip()
    app_secret = getpass.getpass('App secret (typing is hidden): ').strip()
    if not app_key or not app_secret:
        raise LinkError('the app key and the app secret are both needed')
    url = _DL.URL_AUTHORIZE + '?' + urllib.parse.urlencode(
        {'client_id': app_key, 'response_type': 'code', 'token_access_type': 'offline'})
    print('Opening Dropbox in the browser. Press Continue, then Allow, and copy the code it shows.')
    print('If no browser opens, open this address yourself:\n  ' + url)
    webbrowser.open(url)
    code = input('Paste the code here: ').strip()
    got = token_call(app_key, app_secret, {'code': code, 'grant_type': 'authorization_code'})
    if not got.get('refresh_token'):
        raise LinkError('Dropbox gave no refresh token -- run this again')
    check_scopes(got.get('scope', ''))
    report(got['access_token'])
    for name, value in zip(_DL.SECRETS, (app_key, app_secret, got['refresh_token'])):
        secret_put(project, name, value)
        print('[OK] secret written: %s' % name)
    print('[OK] done: the link is in Secret Manager of project %s' % project)
    return True


def check(project: str) -> bool:
    secrets_ready(project)
    app_key, app_secret, refresh = (secret_get(project, n) for n in _DL.SECRETS)
    got = token_call(app_key, app_secret, {'refresh_token': refresh, 'grant_type': 'refresh_token'})
    print('[OK] the three secrets were read from project %s and Dropbox accepted them' % project)
    report(got['access_token'])
    return True


def main() -> bool:
    ap = argparse.ArgumentParser(description='Link the Dropbox account to the photo catalog.')
    ap.add_argument('--check', action='store_true', help='read the secrets back and ask Dropbox who we are')
    ap.add_argument('--project', default='', help='the GCP project (default: the one gcloud is set to)')
    args = ap.parse_args()
    try:
        project = gcp_project(args.project)
        return check(project) if args.check else connect(project)
    except LinkError as exc:
        print('[ERROR] %s' % exc)
    except subprocess.TimeoutExpired:
        print('[ERROR] gcloud did not answer in %d s' % _DL.TIMEOUT_S)
    except KeyboardInterrupt:
        print('\n[ERROR] stopped; nothing more was written')
    return False


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
