"""Shared authentication helper — acquires Power BI token via MSAL.

Uses interactive login (browser popup) with token caching so subsequent
runs within the session are silent.
"""
import sys
import msal
from _config import CLIENT_ID, AUTHORITY, PBI_SCOPES

_token_cache = msal.SerializableTokenCache()
_app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=_token_cache)


def get_pbi_token() -> str:
    """Return a valid Power BI access token (interactive if needed)."""
    accounts = _app.get_accounts()
    result = _app.acquire_token_silent(PBI_SCOPES, account=accounts[0]) if accounts else None
    if not result:
        print("  [Auth] No cached token — launching interactive login...", flush=True)
        result = _app.acquire_token_interactive(scopes=PBI_SCOPES)
    if 'access_token' not in result:
        print(f"  [Auth] FAILED: {result.get('error_description', result)}", file=sys.stderr)
        sys.exit(1)
    return result['access_token']


def get_pbi_headers() -> dict:
    """Return Authorization + Content-Type headers for PBI REST calls."""
    return {
        'Authorization': f'Bearer {get_pbi_token()}',
        'Content-Type': 'application/json'
    }
