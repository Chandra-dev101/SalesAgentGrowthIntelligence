"""Centralized configuration for data source IDs and auth."""
import os

# Azure AD / MSAL
CLIENT_ID = 'ea0616ba-638b-4df5-95b9-636659ae5121'
AUTHORITY = 'https://login.microsoftonline.com/72f988bf-86f1-41af-91ab-2d7cd011db47'
PBI_SCOPES = ['https://analysis.windows.net/powerbi/api/.default']

# Power BI Report/Dataset references
# Source 1: Sales Agent Community app report
PBI_APP_ID_1 = '582c2e01-2b85-4d75-83fe-cc101ed02a3b'
PBI_REPORT_ID_1 = '4b928a5d-f802-4515-8875-cd53ad8206fc'
PBI_REPORT_PAGE_1 = '9b3c6db09bf8279f779c'

# Source 2: Workspace report (consumption/agent data)
PBI_WORKSPACE_ID_2 = '4595703d-63e8-436e-8271-99bdf16c5465'
PBI_REPORT_ID_2 = '22764c5b-fe67-42ef-8f34-3e3128c7900c'
PBI_REPORT_PAGE_2A = '768332c36992a6d56342'  # Agent consumption page
PBI_REPORT_PAGE_2B = '91294d6493b47625525e'  # Whitespace/expansion page

# Source 3: M365 Copilot adoption report
PBI_REPORT_ID_3 = 'd78213e4-f8ae-492b-a1c8-73db84df415a'
PBI_REPORT_PAGE_3 = '187f37427a656b2c4119'

# Analytics Hub (Power Apps portal)
ANALYTICS_HUB_URL = 'https://analytics-hub.powerappsportals.com/Customers/'

# Kusto (for consumption telemetry)
KUSTO_CLUSTER = os.environ.get(
    'SA_GROWTH_KUSTO_CLUSTER',
    'https://d365salestelemetry.westeurope.kusto.windows.net/'
)
KUSTO_DATABASE = 'CRMAnalytics'

# Output paths
DATA_DIR = os.environ.get('SA_GROWTH_DATA_DIR', os.path.expanduser('~'))
OUTPUT_HTML = os.path.join(
    os.path.expanduser('~'),
    'OneDrive - Microsoft',
    'Agent Customer Engagements',
    'Sales Agent Community Expansion Report',
    'SalesAgentGrowthIntelligence.html'
)
