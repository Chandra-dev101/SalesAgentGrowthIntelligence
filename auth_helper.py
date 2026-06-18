"""CI-compatible auth module using cached MSAL refresh tokens.

For local dev: uses interactive login.
For CI (GitHub Actions): uses MSAL_TOKEN_CACHE env var (serialized token cache with refresh tokens).
"""
import os
import msal

TENANT_ID = '72f988bf-86f1-41af-91ab-2d7cd011db47'
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
CLIENT_ID = 'ea0616ba-638b-4df5-95b9-636659ae5121'

IS_CI = os.environ.get('CI', '').lower() in ('true', '1')


def get_token(scopes: list[str]) -> str:
    """Get access token - uses cached refresh token in CI, interactive locally."""
    cache = msal.SerializableTokenCache()

    # In CI, load the cached tokens from the secret
    cache_data = os.environ.get('MSAL_TOKEN_CACHE', '')
    if IS_CI and cache_data:
        cache.deserialize(cache_data)

    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    accounts = app.get_accounts()

    result = None
    if accounts:
        # Try silent refresh first
        result = app.acquire_token_silent(scopes, account=accounts[0])

    if not result or 'access_token' not in result:
        if IS_CI:
            raise RuntimeError(
                f"CI auth failed - refresh token may have expired. "
                f"Re-run token refresh locally and update the MSAL_TOKEN_CACHE secret."
            )
        # Local: fall back to interactive
        result = app.acquire_token_interactive(scopes=scopes)

    if 'access_token' not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")
    return result['access_token']

