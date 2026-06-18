# Sales Agent Growth Intelligence Dashboard

Live data dashboard for the **Microsoft Sales Agents & Copilot Studio Community (CXG)** Fusion program.

## 🔄 Auto-Updates
This dashboard refreshes automatically every day at 9:00 AM ET via GitHub Actions.
You can also trigger a manual refresh from the [Actions tab](../../actions).

## 🌐 View Dashboard
**[Open Dashboard](https://chandra-dev101.github.io/SalesAgentGrowthIntelligence/)**

## Data Sources
- **SuccessHub Dataverse** — Community member list (program participants)
- **Power BI** — Project data (Sales/C4S agents) and CXG customer details

## Setup (for maintainers)
To enable automated refresh, add these repository secrets:
- `AZURE_CLIENT_ID` — App registration client ID
- `AZURE_CLIENT_SECRET` — App registration client secret  
- `AZURE_TENANT_ID` — Azure AD tenant ID (`72f988bf-86f1-41af-91ab-2d7cd011db47`)

The app registration needs:
- **Power BI Service** → Dataset.Read.All (application permission)
- **Dynamics CRM** → user_impersonation or app-level access to SuccessHub
