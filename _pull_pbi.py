"""Pull customer and agent data from Power BI semantic models.

Actual tables discovered via schema probing:
  - Dataset 2 (workspace 4595703d): 'Projects' table (9,706 rows)
  - Dataset 3 (personal, CXG Agents Report): 'Customers' table (17,681 rows), 'Product' table

Output: %USERPROFILE%\\sagi_pbi_data.json
"""
import os, sys, json, requests
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8')

from _config import PBI_WORKSPACE_ID_2, DATA_DIR
from _auth import get_pbi_headers

OUT = os.path.join(DATA_DIR, 'sagi_pbi_data.json')

# Hardcoded dataset IDs discovered via probing
DS2_ID = '0a30b7b3-bafd-40fe-9734-8b176ffce491'  # Projects dataset
DS3_ID = 'a14fd213-5b24-49e5-a156-3f6ca57b6d06'  # CXG Agents Report dataset


def run_dax_workspace(headers, dataset_id, workspace_id, query):
    """Execute DAX against a workspace-scoped dataset."""
    url = f'https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets/{dataset_id}/executeQueries'
    r = requests.post(url, headers=headers, json={
        'queries': [{'query': query}],
        'serializerSettings': {'includeNulls': True}
    })
    if r.status_code == 200:
        return r.json().get('results', [{}])[0].get('tables', [{}])[0].get('rows', [])
    print(f"  DAX ERR ({r.status_code}): {r.text[:500]}")
    return []


def run_dax_personal(headers, dataset_id, query):
    """Execute DAX against a personal (My Workspace) dataset."""
    url = f'https://api.powerbi.com/v1.0/myorg/datasets/{dataset_id}/executeQueries'
    r = requests.post(url, headers=headers, json={
        'queries': [{'query': query}],
        'serializerSettings': {'includeNulls': True}
    })
    if r.status_code == 200:
        return r.json().get('results', [{}])[0].get('tables', [{}])[0].get('rows', [])
    print(f"  DAX ERR ({r.status_code}): {r.text[:500]}")
    return []


def normalize_rows(rows):
    """Strip Power BI's bracket prefix from column names."""
    out = []
    for row in rows:
        cleaned = {}
        for k, v in row.items():
            # 'Projects[Customer Name]' → 'Customer Name'
            clean_key = k.split('[')[-1].rstrip(']') if '[' in k else k.strip('[]')
            cleaned[clean_key] = v
        out.append(cleaned)
    return out


def pull_all():
    headers = get_pbi_headers()
    data = {'pulled_at': datetime.now(timezone.utc).isoformat(), 'sources': {}}

    # --- Source 1: Projects dataset (workspace) — Sales Agent deployment projects ---
    print("[1/3] Pulling Sales Agent Projects from workspace dataset...", flush=True)

    # All Sales/C4S projects with agent deployment info
    q_sales_projects = """
EVALUATE
SELECTCOLUMNS(
    FILTER('Projects',
        'Projects'[Is Sales] = "Yes" || 'Projects'[Is C4S] = "Yes"
    ),
    "CustomerName", 'Projects'[Customer Name],
    "Tenant", 'Projects'[Tenant],
    "TPID", 'Projects'[TPID],
    "ProjectPhase", 'Projects'[Project Phase],
    "ProjectStatus", 'Projects'[Project Overall Status],
    "Status", 'Projects'[Status],
    "AgentProjectType", 'Projects'[Agent Project Type],
    "AgentProjectStage", 'Projects'[Agent Project Stage],
    "Region", 'Projects'[ProjectRegion],
    "IsSales", 'Projects'[Is Sales],
    "IsC4S", 'Projects'[Is C4S],
    "EstGoLive", 'Projects'[Estimated Go Live Date],
    "ActualGoLive", 'Projects'[Actual Go Live Date],
    "ForecastGoLive", 'Projects'[Forecast Go Live Date],
    "ProjectTitle", 'Projects'[Project Title],
    "ProjectManager", 'Projects'[Project Manager Name],
    "CustomerProgram", 'Projects'[Customer Program],
    "Partner", 'Projects'[Partner],
    "CreatedOn", 'Projects'[Created On],
    "LastActive", 'Projects'[Last Active Date],
    "ProjectDuration", 'Projects'[Project Duration (Days)],
    "BeyondEstimate", 'Projects'[Beyond Estimated Go Live Date],
    "POC", 'Projects'[POC],
    "IsCopilotStudio", 'Projects'[Is Copilot Studio],
    "AIProject", 'Projects'[AI Project],
    "Industry", 'Projects'[Project Industry],
    "Country", 'Projects'[Country],
    "LongTermCustomer", 'Projects'[LongTermCustomer],
    "FeatureConsumption", 'Projects'[Feature Message Consumption],
    "ProjectConsumption", 'Projects'[Project Message Consumption],
    "JourneyOwner", 'Projects'[Journey Owner]
)
"""
    rows = run_dax_workspace(headers, DS2_ID, PBI_WORKSPACE_ID_2, q_sales_projects)
    data['sources']['sales_projects'] = normalize_rows(rows)
    print(f"  → {len(rows)} Sales/C4S project rows")

    # Summary counts
    q_summary = """
EVALUATE
ROW(
    "TotalProjects", COUNTROWS('Projects'),
    "SalesProjects", COUNTROWS(FILTER('Projects', 'Projects'[Is Sales] = "Yes")),
    "C4SProjects", COUNTROWS(FILTER('Projects', 'Projects'[Is C4S] = "Yes")),
    "ActiveProjects", COUNTROWS(FILTER('Projects', 'Projects'[Status] = "Active")),
    "DeployInProgress", COUNTROWS(FILTER('Projects', 'Projects'[Agent Project Type] = "Deploy In Progress")),
    "AgentLive", COUNTROWS(FILTER('Projects', CONTAINSSTRING('Projects'[Agent Project Type], "Live")))
)
"""
    rows = run_dax_workspace(headers, DS2_ID, PBI_WORKSPACE_ID_2, q_summary)
    data['sources']['project_summary'] = normalize_rows(rows)
    print(f"  → Summary: {rows}")

    # --- Source 2: CXG Agents Report (personal workspace) — Customer agent status ---
    print("[2/3] Pulling CXG Agents Customers from personal dataset...", flush=True)

    q_customers = """
EVALUATE
SELECTCOLUMNS(
    'Customers',
    "AccountName", 'Customers'[AccountName],
    "TenantId", 'Customers'[TenantId],
    "AllTenantIds", 'Customers'[AllTenantIds],
    "JourneyStatus", 'Customers'[JourneyStatus],
    "CustomerStatus", 'Customers'[CustomerStatus],
    "CustomerStatus_Helix", 'Customers'[CustomerStatus_Helix],
    "JourneyOwner", 'Customers'[JourneyOwner],
    "JourneyName", 'Customers'[JourneyName],
    "JourneyProgram", 'Customers'[JourneyProgram],
    "JourneyIndustry", 'Customers'[JourneyIndustry],
    "JourneyStartDate", 'Customers'[JourneyStartDate],
    "JourneyStatusReason", 'Customers'[JourneyStatusReason],
    "LongTermCustomer", 'Customers'[LongTermCustomer],
    "ReferenceStatus", 'Customers'[ReferenceStatus],
    "AccountId", 'Customers'[AccountId],
    "JourneyId", 'Customers'[JourneyId]
)
"""
    rows = run_dax_personal(headers, DS3_ID, q_customers)
    data['sources']['cxg_customers'] = normalize_rows(rows)
    print(f"  → {len(rows)} CXG customer rows")

    # Customer status breakdown
    q_status = """
EVALUATE
SUMMARIZECOLUMNS(
    'Customers'[CustomerStatus],
    'Customers'[CustomerStatus_Helix],
    "Count", COUNTROWS('Customers')
)
"""
    rows = run_dax_personal(headers, DS3_ID, q_status)
    data['sources']['customer_status_breakdown'] = normalize_rows(rows)
    print(f"  → {len(rows)} status combos")

    # --- Source 3: Products from CXG ---
    print("[3/3] Pulling Products...", flush=True)
    q_products = """
EVALUATE
SELECTCOLUMNS(
    FILTER('Product', 'Product'[Status] = "Active"),
    "ProductName", 'Product'[ProductName],
    "ProductId", 'Product'[productid],
    "ProductLeader", 'Product'[ProductLeader],
    "SLTName", 'Product'[SLTName]
)
"""
    rows = run_dax_personal(headers, DS3_ID, q_products)
    data['sources']['products'] = normalize_rows(rows)
    print(f"  → {len(rows)} products")

    # Save
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved: {OUT}")
    return data


if __name__ == '__main__':
    pull_all()
