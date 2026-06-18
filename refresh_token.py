"""Refresh the MSAL token cache and upload it to GitHub Secrets.

Run this locally every ~90 days to keep the CI pipeline's auth working.
Usage: python refresh_token.py
"""
import sys, os, subprocess, msal
sys.stdout.reconfigure(encoding='utf-8')

CLIENT_ID = 'ea0616ba-638b-4df5-95b9-636659ae5121'
AUTHORITY = 'https://login.microsoftonline.com/72f988bf-86f1-41af-91ab-2d7cd011db47'
REPO = 'Chandra-dev101/SalesAgentGrowthIntelligence'


def main():
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    print("Authenticating for Power BI...", flush=True)
    r1 = app.acquire_token_interactive(scopes=['https://analysis.windows.net/powerbi/api/.default'])
    if 'access_token' not in r1:
        print(f"ERROR: {r1.get('error_description')}")
        return

    print("Authenticating for SuccessHub CRM...", flush=True)
    r2 = app.acquire_token_interactive(scopes=['https://successhub.crm.dynamics.com/.default'])
    if 'access_token' not in r2:
        print(f"ERROR: {r2.get('error_description')}")
        return

    # Upload to GitHub secret
    cache_data = cache.serialize()
    print(f"\n✓ Tokens acquired ({len(cache_data)} bytes)")
    print(f"  Uploading to GitHub secret MSAL_TOKEN_CACHE on {REPO}...")

    proc = subprocess.run(
        ['gh', 'secret', 'set', 'MSAL_TOKEN_CACHE', '-R', REPO],
        input=cache_data, text=True, capture_output=True
    )
    if proc.returncode == 0:
        print("  ✓ Secret updated successfully!")
        print(f"\n  The CI pipeline will use this token for the next ~90 days.")
    else:
        print(f"  ERROR uploading: {proc.stderr}")
        # Save locally as fallback
        with open('msal_cache.json', 'w') as f:
            f.write(cache_data)
        print("  Saved to msal_cache.json — manually upload via GitHub UI.")


if __name__ == '__main__':
    main()
