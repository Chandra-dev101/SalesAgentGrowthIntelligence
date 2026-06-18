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
The automated refresh uses a cached MSAL token (refresh token) stored as a GitHub secret.

**To refresh the token** (needed ~every 90 days when it expires):
1. Run locally: `python refresh_token.py` (launches browser auth)
2. It will update the `MSAL_TOKEN_CACHE` secret automatically

No app registration or service tree ID needed — uses the existing first-party app.
