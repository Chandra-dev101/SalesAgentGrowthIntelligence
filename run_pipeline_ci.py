"""CI pipeline orchestrator for GitHub Actions.

Pulls data from SuccessHub + Power BI, merges, and builds HTML into ./output/index.html.
"""
import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

from auth_helper import get_token, IS_CI

# Output directory for GitHub Pages
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Data cache directory
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.data')
os.makedirs(DATA_DIR, exist_ok=True)


def pull_successhub():
    """Pull community members from SuccessHub Dataverse."""
    import requests
    CRM_URL = 'https://successhub.crm.dynamics.com'
    API_BASE = f'{CRM_URL}/api/data/v9.2'

    scopes = [f'{CRM_URL}/.default']
    token = get_token(scopes)
    headers = {
        'Authorization': f'Bearer {token}',
        'OData-MaxVersion': '4.0',
        'OData-Version': '4.0',
        'Accept': 'application/json',
        'Prefer': 'odata.include-annotations="*",odata.maxpagesize=5000'
    }

    # Find CXG program
    print("  Finding CXG program...", flush=True)
    r = requests.get(
        f"{API_BASE}/campaigns?$filter=contains(name,'Sales Agent') or contains(name,'CXG')&$select=campaignid,name",
        headers=headers
    )
    program_id = None
    if r.status_code == 200:
        for c in r.json().get('value', []):
            name_lower = (c.get('name') or '').lower()
            if 'sales agent' in name_lower and ('cxg' in name_lower or 'copilot studio' in name_lower):
                program_id = c['campaignid']
                break
            elif not program_id and 'sales agent' in name_lower:
                program_id = c['campaignid']

    if not program_id:
        print("  ERROR: Could not find CXG program", flush=True)
        return {'customers': [], 'unique_customers': 0}

    print(f"  Program: {program_id}", flush=True)

    # Pull participants
    all_participants = []
    url = (
        f"{API_BASE}/msdip_programparticipantses"
        f"?$filter=_msdip_program_value eq '{program_id}' and statecode eq 0"
        f"&$select=msdip_name,cat_organizationname,_msdip_organization_value"
    )
    while url:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            print(f"  ERR: {r.status_code}", flush=True)
            break
        data = r.json()
        all_participants.extend(data.get('value', []))
        url = data.get('@odata.nextLink')

    # Deduplicate by org name
    seen = set()
    unique = []
    for p in all_participants:
        org = (p.get('cat_organizationname') or '').strip()
        if org and org not in seen:
            seen.add(org)
            unique.append({'name': org, 'participantName': p.get('msdip_name', '')})

    print(f"  Participants: {len(all_participants)}, Unique orgs: {len(unique)}", flush=True)
    return {'customers': unique, 'unique_customers': len(unique), 'total_participants': len(all_participants)}


def pull_pbi():
    """Pull Power BI data (Projects + Customers)."""
    import requests

    PBI_SCOPES = ['https://analysis.windows.net/powerbi/api/.default']
    token = get_token(PBI_SCOPES)
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    results = {'projects': [], 'customers': []}

    # DS2: Projects (workspace dataset)
    ds2_url = "https://api.powerbi.com/v1.0/myorg/groups/4595703d-63e8-436e-8271-99bdf16c5465/datasets/0a30b7b3-bafd-40fe-9734-8b176ffce491/executeQueries"
    dax = 'EVALUATE SELECTCOLUMNS(FILTER(Projects, Projects[Is Sales]="Yes" || Projects[Is C4S]="Yes"), "CustomerName", Projects[Customer Name], "IsSales", Projects[Is Sales], "IsC4S", Projects[Is C4S], "AgentProjectType", Projects[Agent Project Type], "AgentProjectStage", Projects[Agent Project Stage])'
    r = requests.post(ds2_url, headers=headers, json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}})
    if r.status_code == 200:
        rows = r.json().get('results', [{}])[0].get('tables', [{}])[0].get('rows', [])
        results['projects'] = rows
        print(f"  Projects: {len(rows)}", flush=True)

    # DS3: Customers (personal dataset)
    ds3_url = "https://api.powerbi.com/v1.0/myorg/datasets/a14fd213-5b24-49e5-a156-3f6ca57b6d06/executeQueries"
    dax2 = 'EVALUATE SELECTCOLUMNS(Customers, "AccountName", Customers[AccountName], "CustomerStatus", Customers[CustomerStatus], "Segment", Customers[Segment], "SubSegment", Customers[SubSegment], "Region", Customers[Region], "SubRegion", Customers[SubRegion])'
    r2 = requests.post(ds3_url, headers=headers, json={"queries": [{"query": dax2}], "serializerSettings": {"includeNulls": True}})
    if r2.status_code == 200:
        rows2 = r2.json().get('results', [{}])[0].get('tables', [{}])[0].get('rows', [])
        results['customers'] = rows2
        print(f"  Customers: {len(rows2)}", flush=True)

    return results


def merge_and_build():
    """Main CI pipeline."""
    print("=" * 60)
    print("Sales Agent Growth Intelligence - CI Pipeline")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Step 1: Pull data
    print("\n[1/3] Pulling SuccessHub community members...", flush=True)
    community = pull_successhub()

    print("\n[2/3] Pulling Power BI data...", flush=True)
    pbi = pull_pbi()

    # Step 2: Merge
    print("\n[3/3] Merging and building HTML...", flush=True)
    community_names = {c['name'].lower() for c in community.get('customers', []) if c.get('name')}
    customers_lookup = {}
    for c in pbi.get('customers', []):
        name = (c.get('[AccountName]') or '').strip()
        if name.lower() in community_names:
            customers_lookup[name.lower()] = c

    # Build merged customer records
    merged = []
    for cm in community.get('customers', []):
        name = cm['name']
        cxg = customers_lookup.get(name.lower(), {})
        projects = [p for p in pbi.get('projects', []) if (p.get('[CustomerName]') or '').lower() == name.lower()]

        status = cxg.get('[CustomerStatus]', 'No Active Agents')
        segment = cxg.get('[Segment]', 'Unknown')
        region = cxg.get('[Region]', 'Unknown')

        sales_projects = [p for p in projects if p.get('[IsSales]') == 'Yes']
        c4s_projects = [p for p in projects if p.get('[IsC4S]') == 'Yes']

        merged.append({
            'name': name,
            'status': status,
            'segment': segment,
            'subSegment': cxg.get('[SubSegment]', ''),
            'region': region,
            'subRegion': cxg.get('[SubRegion]', ''),
            'salesProjects': len(sales_projects),
            'c4sProjects': len(c4s_projects),
            'totalProjects': len(projects),
            'agentTypes': list(set(p.get('[AgentProjectType]', '') for p in projects if p.get('[AgentProjectType]'))),
            'stages': list(set(p.get('[AgentProjectStage]', '') for p in projects if p.get('[AgentProjectStage]'))),
        })

    print(f"  Merged: {len(merged)} community customers")

    # Step 3: Build HTML
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template.html')
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Inject data into the last <script> tag
    data_payload = {
        'customers': merged,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'sources': {
            'successHub': community.get('unique_customers', 0),
            'pbiProjects': len(pbi.get('projects', [])),
            'pbiCustomers': len(pbi.get('customers', [])),
        }
    }

    data_json = json.dumps(data_payload, ensure_ascii=False)
    inject_script = f"""<script>
// Live data injected by CI pipeline at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
window.__SAGI_DATA__ = {data_json};
</script>
"""

    # Insert before closing </body>
    html = html.replace('</body>', f'{inject_script}</body>')

    output_file = os.path.join(OUTPUT_DIR, 'index.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✓ Dashboard built: {output_file}")
    print(f"  Community members: {len(merged)}")
    print(f"  Live: {sum(1 for c in merged if c['status']=='Live')}")
    print(f"  With projects: {sum(1 for c in merged if c['totalProjects']>0)}")


if __name__ == '__main__':
    merge_and_build()
