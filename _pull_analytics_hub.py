"""Pull customer list from the Analytics Hub Power Apps portal.

Source: https://analytics-hub.powerappsportals.com/Customers/

The Analytics Hub portal requires Azure AD SSO. This script uses the
MSAL token to call the portal's internal OData API (if available) or
falls back to scraping the rendered HTML.

Output: %USERPROFILE%\\sagi_analytics_hub.json
"""
import os, sys, json, requests
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8')

from _config import ANALYTICS_HUB_URL, DATA_DIR
from _auth import get_pbi_token

OUT = os.path.join(DATA_DIR, 'sagi_analytics_hub.json')


def pull_analytics_hub():
    """Attempt to pull customer data from the Analytics Hub portal."""
    print("Pulling from Analytics Hub...", flush=True)
    print(f"  URL: {ANALYTICS_HUB_URL}")

    token = get_pbi_token()
    headers = {'Authorization': f'Bearer {token}'}

    # Try OData endpoint first (Power Apps portals often expose /_api/...)
    odata_url = ANALYTICS_HUB_URL.rstrip('/') + '/_api/customers'
    print(f"  Trying OData: {odata_url}", flush=True)
    r = requests.get(odata_url, headers=headers, timeout=30)

    data = {'pulled_at': datetime.now(timezone.utc).isoformat(), 'customers': []}

    if r.status_code == 200:
        try:
            odata = r.json()
            data['customers'] = odata.get('value', odata.get('items', []))
            print(f"  → {len(data['customers'])} customers via OData")
        except ValueError:
            print("  OData returned non-JSON, trying HTML...")
            _try_html_parse(headers, data)
    elif r.status_code == 401:
        # Portal may need a different scope — try with the portal's resource
        print("  OData 401 — trying portal resource scope...", flush=True)
        _try_portal_auth(data)
    else:
        print(f"  OData {r.status_code} — trying HTML parse...", flush=True)
        _try_html_parse(headers, data)

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved: {OUT}")
    return data


def _try_portal_auth(data):
    """Try authenticating with the portal's own resource scope."""
    import msal
    from _config import CLIENT_ID, AUTHORITY

    portal_scopes = ['https://analytics-hub.powerappsportals.com/.default']
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(portal_scopes, account=accounts[0]) if accounts else None
    if not result:
        result = app.acquire_token_interactive(scopes=portal_scopes)
    if 'access_token' in result:
        headers = {'Authorization': f'Bearer {result["access_token"]}'}
        odata_url = ANALYTICS_HUB_URL.rstrip('/') + '/_api/customers'
        r = requests.get(odata_url, headers=headers, timeout=30)
        if r.status_code == 200:
            try:
                odata = r.json()
                data['customers'] = odata.get('value', odata.get('items', []))
                print(f"  → {len(data['customers'])} customers via portal auth")
            except ValueError:
                print("  Portal auth: non-JSON response")
        else:
            print(f"  Portal auth: status {r.status_code}")
    else:
        print(f"  Portal auth failed: {result.get('error_description', 'unknown')}")


def _try_html_parse(headers, data):
    """Fallback: fetch the portal HTML and extract customer data from tables."""
    r = requests.get(ANALYTICS_HUB_URL, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  HTML fetch failed: {r.status_code}")
        return

    # Simple table extraction (Power Apps portals render entity lists as tables)
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = False
            self.in_row = False
            self.in_cell = False
            self.headers = []
            self.rows = []
            self.current_row = []
            self.current_cell = ''
            self.header_done = False

        def handle_starttag(self, tag, attrs):
            if tag == 'table':
                self.in_table = True
            elif tag == 'tr' and self.in_table:
                self.in_row = True
                self.current_row = []
            elif tag in ('td', 'th') and self.in_row:
                self.in_cell = True
                self.current_cell = ''

        def handle_endtag(self, tag):
            if tag == 'table':
                self.in_table = False
            elif tag == 'tr' and self.in_row:
                self.in_row = False
                if not self.header_done:
                    self.headers = self.current_row
                    self.header_done = True
                else:
                    self.rows.append(self.current_row)
            elif tag in ('td', 'th') and self.in_cell:
                self.in_cell = False
                self.current_row.append(self.current_cell.strip())

        def handle_data(self, data):
            if self.in_cell:
                self.current_cell += data

    parser = TableParser()
    parser.feed(r.text)

    if parser.headers and parser.rows:
        for row in parser.rows:
            if len(row) == len(parser.headers):
                data['customers'].append(dict(zip(parser.headers, row)))
        print(f"  → {len(data['customers'])} customers from HTML table")
    else:
        print("  No table data found in HTML")


if __name__ == '__main__':
    pull_analytics_hub()
