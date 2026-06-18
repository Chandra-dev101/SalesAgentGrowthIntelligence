"""Pull Fusion Community participants from SuccessHub Dataverse API.

Source: successhub.crm.dynamics.com
Entity: msdip_programparticipants (linked to campaign entity for program)
Filter: Program = "Microsoft Sales Agents & Copilot Studio Community (CXG)"

Output: %USERPROFILE%\\sagi_community_members.json
"""
import os, sys, json, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

import msal
from _config import CLIENT_ID, AUTHORITY, DATA_DIR

OUT = os.path.join(DATA_DIR, 'sagi_community_members.json')

# Dynamics 365 / Dataverse scope for SuccessHub
CRM_URL = 'https://successhub.crm.dynamics.com'
CRM_SCOPES = [f'{CRM_URL}/.default']
API_BASE = f'{CRM_URL}/api/data/v9.2'


def get_crm_token():
    """Acquire token for SuccessHub Dataverse."""
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(CRM_SCOPES, account=accounts[0]) if accounts else None
    if not result:
        print("  [Auth] Launching interactive login for SuccessHub...", flush=True)
        result = app.acquire_token_interactive(scopes=CRM_SCOPES)
    if 'access_token' not in result:
        print(f"  [Auth] FAILED: {result.get('error_description', result)}", file=sys.stderr)
        sys.exit(1)
    return result['access_token']


def pull_community_members():
    print("Pulling Fusion Community participants from SuccessHub...", flush=True)
    token = get_crm_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0',
        'Accept': 'application/json',
        'Prefer': 'odata.include-annotations="*",odata.maxpagesize=5000'
    }

    # Step 1: Find the program (campaign) for Sales Agents CXG community
    print("  Finding program (campaign entity)...", flush=True)
    campaign_url = (
        f"{API_BASE}/campaigns"
        f"?$filter=contains(name,'Sales Agent') or contains(name,'CXG') or contains(name,'Copilot Studio Community')"
        f"&$select=campaignid,name"
    )
    r = requests.get(campaign_url, headers=headers)

    program_id = None
    if r.status_code == 200:
        campaigns = r.json().get('value', [])
        print(f"  Found {len(campaigns)} matching campaigns:")
        for c in campaigns:
            print(f"    - {c.get('name')} (ID: {c.get('campaignid')})")
            name_lower = (c.get('name') or '').lower()
            # Prefer the one specifically for Sales Agents & Copilot Studio Community (CXG)
            if 'sales agent' in name_lower and ('cxg' in name_lower or 'copilot studio' in name_lower):
                program_id = c.get('campaignid')
            elif not program_id and 'sales agent' in name_lower:
                program_id = c.get('campaignid')
        if not program_id and campaigns:
            program_id = campaigns[0].get('campaignid')
        if program_id:
            print(f"  Selected program: {program_id}")
    else:
        print(f"  Campaign query failed ({r.status_code}): {r.text[:400]}")

    if not program_id:
        print("  ERROR: Could not find the Sales Agents CXG program", flush=True)
        # Save empty result
        result = {'pulled_at': '', 'program_id': None, 'total_participants': 0, 'unique_customers': 0, 'customers': []}
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        return result

    # Step 2: Pull all participants for this program
    print(f"  Pulling participants for program {program_id}...", flush=True)
    all_participants = []

    participant_url = (
        f"{API_BASE}/msdip_programparticipantses"
        f"?$filter=_msdip_program_value eq '{program_id}' and statecode eq 0"
        f"&$select=msdip_name,msdip_programparticipantsid,cat_organizationname,_msdip_organization_value"
    )

    page = 1
    while participant_url:
        print(f"    Page {page}...", flush=True)
        r = requests.get(participant_url, headers=headers)
        if r.status_code != 200:
            print(f"    ERR ({r.status_code}): {r.text[:400]}")
            break
        data = r.json()
        batch = data.get('value', [])
        all_participants.extend(batch)
        print(f"    Got {len(batch)} rows (total: {len(all_participants)})")
        participant_url = data.get('@odata.nextLink')
        page += 1

    # Step 3: Extract customer/organization names
    community_customers = []
    for p in all_participants:
        # Organization name from direct field or annotation
        org_name = p.get('cat_organizationname', '')
        if not org_name:
            org_name = p.get('_msdip_organization_value@OData.Community.Display.V1.FormattedValue', '')
        org_id = p.get('_msdip_organization_value', '')

        # Participant name
        participant_name = p.get('msdip_name', '')

        community_customers.append({
            'name': (org_name or '').strip(),
            'participantName': participant_name.strip(),
            'organizationId': org_id or '',
            'participantId': p.get('msdip_programparticipantsid', ''),
        })

    # Deduplicate by organization name
    seen = set()
    unique_customers = []
    for c in community_customers:
        key = c['name']
        if key and key not in seen:
            seen.add(key)
            unique_customers.append(c)

    # Also collect unique participants without org names (use participant name)
    no_org = [c for c in community_customers if not c['name']]
    if no_org:
        print(f"  NOTE: {len(no_org)} participants have no organization name")

    from datetime import datetime, timezone
    result = {
        'pulled_at': datetime.now(timezone.utc).isoformat(),
        'program_id': program_id,
        'total_participants': len(all_participants),
        'unique_customers': len(unique_customers),
        'customers': unique_customers,
    }

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved: {OUT}")
    print(f"  Program ID: {program_id}")
    print(f"  Total participants: {len(all_participants)}")
    print(f"  Unique organizations: {len(unique_customers)}")
    return result


if __name__ == '__main__':
    pull_community_members()
