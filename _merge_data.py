"""Merge data from all sources into a unified customer model.

Reads:
  - sagi_pbi_data.json:
      • sales_projects (DS2 Projects table — Sales/C4S deployment projects)
      • cxg_customers (DS3 Customers table — 17K+ customers with agent status)
      • project_summary (DS2 aggregate counts)
      • customer_status_breakdown (DS3 status distribution)
      • products (DS3 Product table)
  - sagi_kusto_data.json (Kusto telemetry — may be empty if not authorized)
  - sagi_community_members.json (SuccessHub program participants — the authoritative community list)

Output: %USERPROFILE%\\sagi_merged.json — unified customer model ready for HTML rendering.
"""
import os, sys, json
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8')

from _config import DATA_DIR

PBI_FILE = os.path.join(DATA_DIR, 'sagi_pbi_data.json')
KUSTO_FILE = os.path.join(DATA_DIR, 'sagi_kusto_data.json')
COMMUNITY_FILE = os.path.join(DATA_DIR, 'sagi_community_members.json')
OUT = os.path.join(DATA_DIR, 'sagi_merged.json')


def safe_int(v, default=0):
    try:
        return int(float(v)) if v is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def load_json(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    print(f"  WARN: {path} not found — skipping")
    return {}


def map_agent_project_type(apt):
    """Map 'Agent Project Type' to a deployment status."""
    if not apt:
        return 'None'
    apt = str(apt).lower()
    if 'live' in apt:
        return 'Live'
    if 'deploy' in apt:
        return 'Deploy'
    if 'poc' in apt or 'pilot' in apt:
        return 'POC'
    if 'implement' in apt or 'initiate' in apt or 'prepare' in apt:
        return 'Deploy'
    return 'Presales'


def map_customer_status(cs):
    """Map CXG CustomerStatus to a simplified tier."""
    if not cs:
        return 'None'
    cs = str(cs).strip()
    if cs == 'Live':
        return 'Live'
    if cs == 'POC':
        return 'POC'
    if cs == 'Implement':
        return 'Deploy'
    if cs == 'No Active Agents':
        return 'None'
    return cs


def merge():
    print("Merging data sources...", flush=True)
    pbi = load_json(PBI_FILE)
    kusto = load_json(KUSTO_FILE)
    community = load_json(COMMUNITY_FILE)

    # --- Parse SuccessHub Community Members (authoritative filter) ---
    community_members = community.get('customers', [])
    community_names = set()
    for m in community_members:
        name = (m.get('name') or '').strip()
        if name:
            community_names.add(name)
    print(f"  SuccessHub community members: {len(community_names)}")

    # --- Parse DS2: Sales/C4S Projects ---
    sales_projects = pbi.get('sources', {}).get('sales_projects', [])
    print(f"  Sales/C4S projects: {len(sales_projects)}")

    # Group projects by customer name (one customer can have multiple projects)
    project_by_customer = {}
    for proj in sales_projects:
        name = (proj.get('CustomerName') or '').strip()
        if not name:
            continue
        if name not in project_by_customer:
            project_by_customer[name] = []
        project_by_customer[name].append(proj)

    # --- Parse DS3: CXG Customers ---
    cxg_customers = pbi.get('sources', {}).get('cxg_customers', [])
    print(f"  CXG customers: {len(cxg_customers)}")

    cxg_by_name = {}
    cxg_by_tid = {}
    for cust in cxg_customers:
        name = (cust.get('AccountName') or cust.get('JourneyName') or '').strip()
        tid = (cust.get('TenantId') or '').strip()
        if name:
            cxg_by_name[name] = cust
        if tid:
            cxg_by_tid[tid] = cust

    # --- Parse Kusto consumption (may be empty) ---
    kusto_consumption = {}
    for row in kusto.get('consumption', []):
        tid = str(row.get('TenantID', '')).strip()
        if tid:
            kusto_consumption[tid] = row

    # --- Project summary from DS2 ---
    proj_summary = pbi.get('sources', {}).get('project_summary', [{}])
    if proj_summary:
        ps = proj_summary[0] if isinstance(proj_summary, list) else proj_summary
    else:
        ps = {}

    # --- Build unified customer list ---
    # ONLY include customers from the SuccessHub community program
    # If community list is available, use it as the authoritative filter
    # Otherwise fall back to DS2 project customers
    if community_names:
        all_customer_names = community_names
        print(f"  Using SuccessHub community list: {len(all_customer_names)} customers")
    else:
        all_customer_names = set(project_by_customer.keys())
        print(f"  Fallback to DS2 project customers: {len(all_customer_names)}")

    # Agent type keys for the dashboard
    agent_keys = ['Qualification', 'Opportunity', 'Development', 'Research', 'Close']

    customers = []
    for name in sorted(all_customer_names):
        cxg = cxg_by_name.get(name, {})
        projs = project_by_customer.get(name, [])

        tid = (cxg.get('TenantId') or '').strip()
        if not tid:
            # Try to get from projects
            for p in projs:
                t = (p.get('Tenant') or '').strip()
                if t:
                    tid = t
                    break

        # Agent status from CXG
        customer_status = cxg.get('CustomerStatus', 'No Active Agents')
        customer_status_helix = cxg.get('CustomerStatus_Helix', customer_status)
        agent_tier = map_customer_status(customer_status)

        # Industry and region from projects or CXG
        industry = ''
        region = ''
        for p in projs:
            if p.get('Industry'):
                industry = p['Industry']
            if p.get('Region'):
                region = p['Region']
        if not industry:
            industry = cxg.get('JourneyIndustry', '') or ''

        # Agent deployment: derive from projects
        # Count distinct agent project types
        project_statuses = [map_agent_project_type(p.get('AgentProjectType')) for p in projs]
        live_count = sum(1 for s in project_statuses if s == 'Live')
        deploy_count = sum(1 for s in project_statuses if s == 'Deploy')
        poc_count = sum(1 for s in project_statuses if s == 'POC')
        total_projects = len(projs)

        # Is this a Sales agent project customer?
        is_sales = any(p.get('IsSales') == 'Yes' for p in projs)
        is_c4s = any(p.get('IsC4S') == 'Yes' for p in projs)

        # Fusion stage from project data
        has_projects = len(projs) > 0
        fusion_stage = None
        if has_projects:
            # Determine stage from most advanced project
            if live_count > 0:
                fusion_stage = 'Deployed'
            elif deploy_count > 0:
                fusion_stage = 'Active'
            elif poc_count > 0:
                fusion_stage = 'Onboarding'
            else:
                fusion_stage = 'Planning'

        # Build owned agents dict — map projects to agent types heuristically
        owned_agents = {k: '—' for k in agent_keys}
        if agent_tier == 'Live' or live_count > 0:
            # Assign based on project count
            for i, ak in enumerate(agent_keys):
                if i < live_count:
                    owned_agents[ak] = 'Live'
                elif i < live_count + deploy_count:
                    owned_agents[ak] = 'Deploy'
                elif i < live_count + deploy_count + poc_count:
                    owned_agents[ak] = 'POC'
        elif agent_tier == 'Deploy' or deploy_count > 0:
            for i, ak in enumerate(agent_keys):
                if i < deploy_count:
                    owned_agents[ak] = 'Deploy'
                elif i < deploy_count + poc_count:
                    owned_agents[ak] = 'POC'
        elif agent_tier == 'POC' or poc_count > 0:
            for i, ak in enumerate(agent_keys):
                if i < poc_count:
                    owned_agents[ak] = 'POC'

        owned_count = sum(1 for s in owned_agents.values() if s != '—')
        live_agents = sum(1 for s in owned_agents.values() if s == 'Live')

        # Kusto consumption data (if available)
        kust = kusto_consumption.get(tid, {})
        mau = safe_int(kust.get('MAU'))
        pru = safe_float(kust.get('PRU'))
        agent_mau = safe_int(kust.get('Agent_MAU'))
        credits_30d = safe_int(kust.get('Credits_30d'))
        credits_90d = safe_int(kust.get('Credits_90d'))
        copilot_mau = safe_int(kust.get('Copilot_MAU'))
        growth_trend = safe_float(kust.get('Growth_Trend'))

        # If no Kusto data, estimate from project status
        if not kust and agent_tier == 'Live':
            mau = 100  # placeholder
            credits_30d = 50
            credits_90d = 150

        # Consumption metrics
        seats = 0
        d365_lic = 0
        d365_edition = 'None'
        copilot_lic = 0
        m365_e5 = 'None'
        total_credits = credits_90d * 2 if credits_90d else 0
        used_credits = credits_90d
        unused_credits = max(0, total_credits - used_credits)

        # Consumption score
        if mau or credits_90d or pru:
            c_norm = min(used_credits / 50000, 1) * 100 if used_credits else 0
            m_norm = min(mau / 20000, 1) * 100 if mau else 0
            g_norm = max(0, min((growth_trend + 15) / 55 * 100, 100))
            consumption_score = round(c_norm * 0.4 + m_norm * 0.2 + pru * 0.2 + g_norm * 0.2)
        else:
            # Score based on project status
            if agent_tier == 'Live':
                consumption_score = 60
            elif agent_tier == 'Deploy':
                consumption_score = 40
            elif agent_tier == 'POC':
                consumption_score = 25
            else:
                consumption_score = 10

        tier = 'Green' if consumption_score >= 60 else 'Yellow' if consumption_score >= 35 else 'Red'

        # Whitespace score
        if agent_tier == 'None' and has_projects:
            ws_score = 70
        elif agent_tier == 'None':
            ws_score = 85
        elif agent_tier in ('POC', 'Deploy'):
            ws_score = 50
        elif owned_count < 3:
            ws_score = 40
        else:
            ws_score = 15

        # Opportunity
        if agent_tier == 'None':
            opp_category = 'Activation'
        elif owned_count < 3:
            opp_category = 'Expansion'
        elif agent_tier in ('POC', 'Deploy'):
            opp_category = 'Cross-Sell'
        else:
            opp_category = 'Upsell'
        opp_score = consumption_score

        # Next agent recommendation
        has_a = lambda a: owned_agents.get(a, '—') != '—'
        if not any(has_a(a) for a in agent_keys):
            rec_agent, rec_reason = 'Qualification', 'No agents — start with Qualification'
        elif has_a('Qualification') and not has_a('Opportunity'):
            rec_agent, rec_reason = 'Opportunity', 'Has Qualification → natural progression'
        elif has_a('Opportunity') and not has_a('Close'):
            rec_agent, rec_reason = 'Close', 'Has Opportunity → complete funnel'
        elif has_a('Opportunity') and has_a('Close') and not has_a('Development'):
            rec_agent, rec_reason = 'Development', 'Has Opp + Close → add Development'
        elif has_a('Development') and not has_a('Research'):
            rec_agent, rec_reason = 'Research', 'Has Development → add Research'
        elif live_agents == 5:
            rec_agent, rec_reason = '—', 'Full adoption — focus on consumption'
        else:
            rec_agent, rec_reason = 'Qualification', 'Fill gaps'

        # Expansion score
        exp_score = 0
        if agent_tier == 'None':
            exp_score += 25
        elif agent_tier in ('POC', 'Deploy'):
            exp_score += 15
        if owned_count < 3:
            exp_score += 15
        if total_projects > 0:
            exp_score += 10
        if not kust:
            exp_score += 20  # no telemetry = likely not consuming
        exp_score = min(exp_score, 100)
        exp_category = 'Critical' if exp_score >= 80 else 'High' if exp_score >= 60 else 'Medium' if exp_score >= 40 else 'Low'

        # Utilization
        utilization = round((copilot_mau / max(copilot_lic, 1)) * 100) if copilot_lic else 0

        # Classification
        if credits_30d > 5000:
            consumption_class = 'High'
        elif credits_30d > 1000:
            consumption_class = 'Medium'
        elif credits_30d > 0:
            consumption_class = 'Low'
        else:
            consumption_class = 'None'

        agent_gap = max(0, round(copilot_mau * 0.1) - agent_mau) if copilot_mau else 0

        # Project duration for "stalled" detection
        max_duration = max((safe_int(p.get('ProjectDuration')) for p in projs), default=0)

        customers.append({
            'name': name,
            'tenantId': tid,
            'industry': industry,
            'segment': '',
            'region': region,
            'seats': seats,
            'd365Lic': d365_lic,
            'd365Edition': d365_edition,
            'm365E5': m365_e5,
            'copilotLic': copilot_lic,
            'copilotMAU': copilot_mau,
            'totalCredits': total_credits,
            'usedCredits': used_credits,
            'unusedCredits': unused_credits,
            'mau': mau,
            'pru': round(pru, 1),
            'agentMAU': agent_mau,
            'growthTrend': round(growth_trend, 1),
            'credits30d': credits_30d,
            'credits90d': credits_90d,
            'consumptionScore': consumption_score,
            'tier': tier,
            'ownedAgents': owned_agents,
            'liveAgents': live_agents,
            'ownedCount': owned_count,
            'recommendedAgent': rec_agent,
            'recReason': rec_reason,
            'wsScore': ws_score,
            'oppCategory': opp_category,
            'oppScore': opp_score,
            'estRevenue': 0,
            'expScore': exp_score,
            'expCategory': exp_category,
            'isFusion': has_projects,
            'fusionStage': fusion_stage,
            'utilization': utilization,
            'consumptionClass': consumption_class,
            'agentGap': agent_gap,
            'customerStatus': customer_status,
            'customerStatusHelix': customer_status_helix,
            'totalProjects': total_projects,
            'daysStalled': max_duration if agent_tier in ('Deploy', 'POC') else 0,
            'journeyOwner': cxg.get('JourneyOwner', ''),
            'isSales': is_sales,
            'isC4S': is_c4s,
        })

    # Sort by consumption score descending, then by project count
    customers.sort(key=lambda c: (c['consumptionScore'], c['totalProjects']), reverse=True)

    # Compute summary KPIs
    total_customers = len(customers)
    with_projects = sum(1 for c in customers if c['isFusion'])
    live_customers = sum(1 for c in customers if c['customerStatus'] == 'Live')
    deploy_customers = sum(1 for c in customers if c['customerStatus'] == 'Implement')
    poc_customers = sum(1 for c in customers if c['customerStatus'] == 'POC')
    no_agents = sum(1 for c in customers if c['customerStatus'] == 'No Active Agents')
    sales_customers = sum(1 for c in customers if c['isSales'])

    merged = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'kpis': {
            'total_customers': total_customers,
            'with_projects': with_projects,
            'live_customers': live_customers,
            'deploy_customers': deploy_customers,
            'poc_customers': poc_customers,
            'no_agents': no_agents,
            'sales_customers': sales_customers,
            'active_agent_customers': live_customers + deploy_customers + poc_customers,
            'total_credits_consumed': sum(c['usedCredits'] for c in customers),
            'total_copilot_mau': sum(c['copilotMAU'] for c in customers),
            'avg_pru': round(sum(c['pru'] for c in customers) / max(total_customers, 1), 1),
            'whitespace_revenue': 0,
            'total_projects_ds2': safe_int(ps.get('TotalProjects')),
            'sales_projects_ds2': safe_int(ps.get('SalesProjects')),
            'c4s_projects_ds2': safe_int(ps.get('C4SProjects')),
            'deploy_in_progress_ds2': safe_int(ps.get('DeployInProgress')),
            'agent_live_ds2': safe_int(ps.get('AgentLive')),
        },
        'customer_status_breakdown': pbi.get('sources', {}).get('customer_status_breakdown', []),
        'monthly_trend': kusto.get('monthly_trend', []),
        'agent_status': kusto.get('agent_status', []),
        'customers': customers,
    }

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Merged {total_customers} customers → {OUT}")
    print(f"  Live: {live_customers}, Deploy: {deploy_customers}, POC: {poc_customers}, No Agents: {no_agents}")
    print(f"  Sales projects: {sales_customers}, With any projects: {with_projects}")
    return merged


if __name__ == '__main__':
    merge()
