"""Pull Kusto consumption telemetry for Sales Agent usage.

Source: d365salestelemetry Kusto cluster, CRMAnalytics database.
Pulls per-tenant MAU, credits, trends.

Output: %USERPROFILE%\\sagi_kusto_data.json
"""
import os, sys, json
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8')

from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.helpers import dataframe_from_result_table

from _config import KUSTO_CLUSTER, KUSTO_DATABASE, DATA_DIR

OUT = os.path.join(DATA_DIR, 'sagi_kusto_data.json')

# KQL: Per-tenant consumption with 30d/90d breakdown and trends
KQL_CONSUMPTION = """
let latestDate = toscalar(CopilotForSalesUsageFactMonthlyActiveUsers | summarize max(Date));
let d30 = datetime_add('day', -30, latestDate);
let d90 = datetime_add('day', -90, latestDate);
CopilotForSalesUsageFactMonthlyActiveUsers
| where Date >= d90
| summarize
    MAU = sumif(M365TotalActiveUserCount, Date == latestDate),
    MAU_30d_ago = sumif(M365TotalActiveUserCount, Date >= d30 and Date < latestDate),
    Credits_30d = sumif(TotalCreditsConsumed, Date >= d30),
    Credits_90d = sum(TotalCreditsConsumed),
    Agent_MAU = sumif(AgentActiveUserCount, Date == latestDate),
    PRU = avgif(PaidRetainedUsagePct, Date == latestDate),
    Copilot_MAU = sumif(M365CopilotActiveUserCount, Date == latestDate)
    by TenantID
| extend Growth_Trend = iff(MAU_30d_ago > 0, round((todouble(MAU) - MAU_30d_ago) / MAU_30d_ago * 100, 1), 0.0)
| project TenantID, MAU, Credits_30d, Credits_90d, Agent_MAU, PRU, Copilot_MAU, Growth_Trend
| order by Credits_90d desc
"""

# KQL: Monthly trend for executive chart (last 12 months)
KQL_MONTHLY_TREND = """
CopilotForSalesUsageFactMonthlyActiveUsers
| where Date >= ago(365d)
| summarize
    Total_Credits = sum(TotalCreditsConsumed),
    Total_MAU = sum(M365TotalActiveUserCount)
    by Month = startofmonth(Date)
| order by Month asc
"""

# KQL: Agent deployment status counts
KQL_AGENT_STATUS = """
SalesAgentDeploymentStatus
| summarize
    Live = countif(Status == "Live"),
    Deploy = countif(Status == "Deploy"),
    POC = countif(Status == "POC"),
    Presales = countif(Status == "Presales")
    by AgentName
"""


def pull_kusto():
    print(f"Kusto cluster: {KUSTO_CLUSTER}", flush=True)
    print(f"Database: {KUSTO_DATABASE}", flush=True)
    print("Authenticating (interactive login)...", flush=True)

    kcsb = KustoConnectionStringBuilder.with_interactive_login(KUSTO_CLUSTER)
    client = KustoClient(kcsb)

    data = {'pulled_at': datetime.now(timezone.utc).isoformat()}

    # Query 1: Consumption per tenant
    print("Running KQL: per-tenant consumption...", flush=True)
    try:
        resp = client.execute(KUSTO_DATABASE, KQL_CONSUMPTION)
        df = dataframe_from_result_table(resp.primary_results[0])
        data['consumption'] = df.to_dict(orient='records')
        print(f"  → {len(df):,} tenant rows")
    except Exception as e:
        print(f"  WARN: consumption query failed: {e}")
        data['consumption'] = []

    # Query 2: Monthly trend
    print("Running KQL: monthly trend...", flush=True)
    try:
        resp = client.execute(KUSTO_DATABASE, KQL_MONTHLY_TREND)
        df = dataframe_from_result_table(resp.primary_results[0])
        data['monthly_trend'] = df.to_dict(orient='records')
        print(f"  → {len(df)} months")
    except Exception as e:
        print(f"  WARN: monthly trend query failed: {e}")
        data['monthly_trend'] = []

    # Query 3: Agent status
    print("Running KQL: agent deployment status...", flush=True)
    try:
        resp = client.execute(KUSTO_DATABASE, KQL_AGENT_STATUS)
        df = dataframe_from_result_table(resp.primary_results[0])
        data['agent_status'] = df.to_dict(orient='records')
        print(f"  → {len(df)} agent types")
    except Exception as e:
        print(f"  WARN: agent status query failed: {e}")
        data['agent_status'] = []

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n✓ Saved: {OUT}")
    return data


if __name__ == '__main__':
    pull_kusto()
