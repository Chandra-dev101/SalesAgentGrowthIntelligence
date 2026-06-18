"""CI-compatible auth module using client credentials (service principal).

For local dev: uses interactive login (same as before).
For CI (GitHub Actions): uses AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID env vars.
"""
import os
import msal

TENANT_ID = os.environ.get('AZURE_TENANT_ID', '72f988bf-86f1-41af-91ab-2d7cd011db47')
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'

# For CI: app registration with client secret
CLIENT_ID_CI = os.environ.get('AZURE_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('AZURE_CLIENT_SECRET', '')

# For local interactive
CLIENT_ID_LOCAL = 'ea0616ba-638b-4df5-95b9-636659ae5121'

IS_CI = os.environ.get('CI', '').lower() in ('true', '1')


def get_token(scopes: list[str]) -> str:
    """Get access token - uses service principal in CI, interactive locally."""
    if IS_CI and CLIENT_ID_CI and CLIENT_SECRET:
        app = msal.ConfidentialClientApplication(
            CLIENT_ID_CI,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET
        )
        result = app.acquire_token_for_client(scopes=scopes)
    else:
        app = msal.PublicClientApplication(CLIENT_ID_LOCAL, authority=AUTHORITY)
        accounts = app.get_accounts()
        result = app.acquire_token_silent(scopes, account=accounts[0]) if accounts else None
        if not result:
            result = app.acquire_token_interactive(scopes=scopes)

    if 'access_token' not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")
    return result['access_token']
