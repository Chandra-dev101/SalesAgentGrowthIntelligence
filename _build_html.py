"""Build the SalesAgentGrowthIntelligence.html with real data.

Reads: %USERPROFILE%\\sagi_merged.json
Output: The final HTML file with live data embedded as a JSON constant.

Strategy: Replace ONLY the data-generation portion of the script (the RNG/fake
data section) with a `const customers = [...]` literal from merged data.
The render helpers and UI code are preserved as-is.
"""
import os, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')

from _config import DATA_DIR, OUTPUT_HTML

MERGED_FILE = os.path.join(DATA_DIR, 'sagi_merged.json')


def build_html():
    print("Building HTML with live data...", flush=True)

    if not os.path.exists(MERGED_FILE):
        print(f"ERROR: {MERGED_FILE} not found. Run the pipeline first.", file=sys.stderr)
        sys.exit(1)

    with open(MERGED_FILE, 'r', encoding='utf-8') as f:
        merged = json.load(f)

    if not os.path.exists(OUTPUT_HTML):
        print(f"ERROR: Template HTML not found at {OUTPUT_HTML}", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_HTML, 'r', encoding='utf-8') as f:
        html = f.read()

    generated_at = merged.get('generated_at', 'unknown')
    customers = merged['customers']
    kpis = merged['kpis']

    # Build the replacement data section
    # Find the LAST/MAIN <script> tag (not the small theme-detection one at the top)
    # The main data script contains "Deterministic RNG" or "customers"
    last_script_start = html.rfind('<script>')
    last_script_end = html.rfind('</script>')
    if last_script_start == -1 or last_script_end == -1:
        print("ERROR: Could not find <script> tags in HTML", file=sys.stderr)
        sys.exit(1)

    script_start = last_script_start + len('<script>')
    script_end = last_script_end
    old_script = html[script_start:script_end]

    # Find where render code begins — look for the first function definition after data gen
    # Markers to try (in order of preference)
    markers = [
        'function tierBadge',
        'function scoreBubble',
        'function statusBadge',
        '// ─── Render Helpers',
        'function fmt(',
    ]

    render_start_idx = -1
    for marker in markers:
        idx = old_script.find(marker)
        if idx != -1:
            render_start_idx = idx
            break

    if render_start_idx == -1:
        # Fallback: find the first "function" that's clearly a render helper
        # Skip past customers.sort line
        sort_idx = old_script.find('customers.sort(')
        if sort_idx != -1:
            render_start_idx = old_script.find('\nfunction ', sort_idx)
            if render_start_idx != -1:
                render_start_idx += 1  # skip the \n
        if render_start_idx == -1:
            print("ERROR: Could not find render section boundary in script", file=sys.stderr)
            print("  Trying alternative approach: full script replacement...", flush=True)
            render_start_idx = None

    # Build data injection script
    customers_json = json.dumps(customers, ensure_ascii=False)
    kpis_json = json.dumps(kpis, ensure_ascii=False)

    data_script = f"""
// ═══ LIVE DATA — Generated {generated_at} ═══
// Source: Power BI + Kusto + Analytics Hub pipeline
const _LIVE = true;
const _kpis = {kpis_json};
const customers = {customers_json};

// Compatibility fields
customers.forEach(c => {{
  c.currentAgents = Object.entries(c.ownedAgents || {{}}).filter(([,s]) => s !== '—').map(([a]) => a);
  c.expectedValue = c.estRevenue || 0;
  if (!c.daysStalled) c.daysStalled = 0;
}});
customers.sort((a, b) => b.consumptionScore - a.consumptionScore);
const fusionCustomers = customers.filter(c => c.isFusion);

// Helper functions
function fmt(n) {{ return (n || 0).toLocaleString(); }}
function fmtUSD(n) {{ return '$' + (n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(0)+'K' : (n||0).toLocaleString()); }}

"""

    if render_start_idx is not None:
        # Keep the render code from render_start_idx onward
        render_code = old_script[render_start_idx:]

        # Patch the Executive KPIs to use live data
        exec_kpi_pattern = r"makeKPIs\('exec-kpis',\[.*?\]\);"
        exec_kpi_replacement = """makeKPIs('exec-kpis',[
  {label:'Total Customers',value:fmt(_kpis.total_customers),delta:_kpis.with_projects+' with projects',deltaClass:'up'},
  {label:'Active Agent Customers',value:fmt(_kpis.active_agent_customers),delta:'Live+Deploy+POC',deltaClass:'up'},
  {label:'Agent Live (DS2)',value:fmt(_kpis.agent_live_ds2),delta:'From project data',deltaClass:'up'},
  {label:'Deploy In Progress',value:fmt(_kpis.deploy_in_progress_ds2),delta:'Active deployments',deltaClass:'up'},
  {label:'Sales Projects',value:fmt(_kpis.sales_projects_ds2),delta:'Sales agent focused',deltaClass:'up'},
  {label:'No Agents',value:fmt(_kpis.no_agents),delta:'Whitespace opportunity',deltaClass:'down'}
]);"""
        render_code = re.sub(exec_kpi_pattern, exec_kpi_replacement, render_code, flags=re.DOTALL)

        # Patch consumption KPIs
        cons_kpi_pattern = r"makeKPIs\('consumption-kpis',\[.*?\]\);"
        cons_kpi_replacement = """makeKPIs('consumption-kpis',[
  {label:'Total Customers',value:fmt(customers.length),delta:'From all sources',deltaClass:'up'},
  {label:'Green Tier',value:String(customers.filter(c=>c.tier==='Green').length),delta:Math.round(customers.filter(c=>c.tier==='Green').length/Math.max(customers.length,1)*100)+'%',deltaClass:'up'},
  {label:'Yellow Tier',value:String(customers.filter(c=>c.tier==='Yellow').length),delta:'In progress',deltaClass:'flat'},
  {label:'Red Tier',value:String(customers.filter(c=>c.tier==='Red').length),delta:'Needs attention',deltaClass:'down'}
]);"""
        render_code = re.sub(cons_kpi_pattern, cons_kpi_replacement, render_code, flags=re.DOTALL)

        # Patch copilot KPIs
        cop_kpi_pattern = r"makeKPIs\('copilot-kpis',\[.*?\]\);"
        cop_kpi_replacement = """makeKPIs('copilot-kpis',[
  {label:'Live Customers',value:fmt(_kpis.live_customers),delta:'Agent status: Live',deltaClass:'up'},
  {label:'POC Customers',value:fmt(_kpis.poc_customers),delta:'In proof-of-concept',deltaClass:'flat'},
  {label:'Deploy Customers',value:fmt(_kpis.deploy_customers),delta:'Implementation',deltaClass:'up'},
  {label:'No Agents',value:fmt(_kpis.no_agents),delta:'Opportunity',deltaClass:'down'}
]);"""
        render_code = re.sub(cop_kpi_pattern, cop_kpi_replacement, render_code, flags=re.DOTALL)

        # Patch the monthly trend chart (remove RNG-based data)
        trend_pattern = r"const months=\[.*?\];\s*const trendData=.*?;\s*trendData\.forEach.*?;\s*renderBarChart\('exec-trend-chart'.*?\);"
        trend_replacement = """// Monthly trend not available without Kusto access
renderBarChart('exec-trend-chart', [{label:'Data requires Kusto access',value:0,display:'N/A'}], 1, ()=>'accent');"""
        render_code = re.sub(trend_pattern, trend_replacement, render_code, flags=re.DOTALL)

        new_script = data_script + render_code
    else:
        # Full replacement — build a minimal render script
        new_script = data_script + _build_minimal_render()

    # Reconstruct HTML
    new_html = html[:script_start] + "\n" + new_script + "\n" + html[script_end:]

    # Add generation timestamp
    if '<!-- Generated with live data' not in new_html:
        new_html = new_html.replace('<!DOCTYPE html>',
                                    f'<!-- Generated with live data on {generated_at} -->\n<!DOCTYPE html>', 1)

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(new_html)
    print(f"✓ HTML written: {OUTPUT_HTML}")
    print(f"  Customers: {len(customers)}")
    print(f"  Generated: {generated_at}")


def _build_minimal_render():
    """Fallback: minimal render code if we can't preserve the original."""
    return """
function tierBadge(t){const c=t==='Green'?'badge-green':t==='Yellow'?'badge-yellow':'badge-red';return`<span class="badge ${c}">${t}</span>`;}
function scoreBubble(s){const c=s>=60?'score-green':s>=35?'score-yellow':'score-red';return`<div class="score-circle ${c}">${s}</div>`;}
function statusBadge(s){
  if(s==='—')return'<span class="status-dot none" title="Not Owned"></span>';
  const d=s==='Live'?'live':s==='Deploy'?'deploy':s==='POC'?'poc':'presales';
  return`<span class="matrix-status"><span class="status-dot ${d}"></span> ${s}</span>`;
}
function trendArrow(v){
  if(v>0)return`<span style="color:var(--cp-success)">↑${v}%</span>`;
  if(v<0)return`<span style="color:var(--cp-danger)">↓${Math.abs(v)}%</span>`;
  return`<span style="color:var(--cp-warning)">→0%</span>`;
}
function progressBar(p){const c=p>=60?'progress-green':p>=35?'progress-yellow':'progress-red';return`<div class="progress-bar ${c}"><div class="progress-fill" style="width:${Math.min(p,100)}%"></div></div>`;}
function classificationBadge(c){return c==='High'?'<span class="badge badge-green">High</span>':c==='Medium'?'<span class="badge badge-yellow">Medium</span>':c==='Low'?'<span class="badge badge-red">Low</span>':'<span class="badge badge-muted">None</span>';}
function expCategoryBadge(c){return c==='Critical'?'<span class="badge badge-red">Critical</span>':c==='High'?'<span class="badge badge-yellow">High</span>':c==='Medium'?'<span class="badge badge-blue">Medium</span>':'<span class="badge badge-green">Low</span>';}
function d365EdBadge(e){return e==='Premium'?'<span class="badge badge-green">Premium</span>':e==='Enterprise'?'<span class="badge badge-blue">Enterprise</span>':'<span class="badge badge-muted">—</span>';}
function m365E5Badge(s){return s==='Owned'?'<span class="badge badge-green">Owned</span>':s==='Pipeline'?'<span class="badge badge-yellow">Pipeline</span>':'<span class="badge badge-muted">—</span>';}

function renderBarChart(id,data,max,colorFn){
  const el=document.getElementById(id);if(!el)return;
  el.innerHTML=data.map(d=>{
    const p=(d.value/max)*100;const color=colorFn?colorFn(d):'accent';
    return`<div class="bar-row"><span class="bar-label">${d.label}</span><div class="bar-track"><div class="bar-fill ${color}" style="width:${p}%">${p>15?(d.display||fmt(d.value)):''}</div></div><span class="bar-value">${d.display||fmt(d.value)}</span></div>`;
  }).join('');
}

function makeKPIs(containerId, kpis){
  const el=document.getElementById(containerId);if(!el)return;
  el.innerHTML=kpis.map(k=>`<div class="kpi-card${k.highlight?' highlight':''}"><div class="kpi-label">${k.label}</div><div class="kpi-value">${k.value}</div><div class="kpi-delta ${k.deltaClass||''}">${k.delta}</div></div>`).join('');
}

// Executive KPIs
makeKPIs('exec-kpis',[
  {label:'Total Customers',value:fmt(_kpis.total_customers),delta:_kpis.with_projects+' with projects',deltaClass:'up'},
  {label:'Active Agent Customers',value:fmt(_kpis.active_agent_customers),delta:'Live+Deploy+POC',deltaClass:'up'},
  {label:'Agent Live',value:fmt(_kpis.agent_live_ds2),delta:'From project data',deltaClass:'up'},
  {label:'Deploy In Progress',value:fmt(_kpis.deploy_in_progress_ds2),delta:'Active deployments',deltaClass:'up'},
  {label:'Sales Projects',value:fmt(_kpis.sales_projects_ds2),delta:'Sales agent focused',deltaClass:'up'},
  {label:'No Agents',value:fmt(_kpis.no_agents),delta:'Whitespace',deltaClass:'down'}
]);

// Agent type chart
renderBarChart('exec-agent-chart',[
  {label:'Qualification Agent',value:customers.filter(c=>c.ownedAgents.Qualification!=='—').length},
  {label:'Opportunity Agent',value:customers.filter(c=>c.ownedAgents.Opportunity!=='—').length},
  {label:'Development Agent',value:customers.filter(c=>c.ownedAgents.Development!=='—').length},
  {label:'Research Agent',value:customers.filter(c=>c.ownedAgents.Research!=='—').length},
  {label:'Close Agent',value:customers.filter(c=>c.ownedAgents.Close!=='—').length}
],Math.max(customers.length,1),()=>'accent');

renderBarChart('exec-tier-chart',[
  {label:'Green (Score ≥ 60)',value:customers.filter(c=>c.tier==='Green').length},
  {label:'Yellow (Score 35-59)',value:customers.filter(c=>c.tier==='Yellow').length},
  {label:'Red (Score < 35)',value:customers.filter(c=>c.tier==='Red').length}
],Math.max(customers.length,1),d=>d.label.includes('Green')?'success':d.label.includes('Yellow')?'warning':'danger');

renderBarChart('exec-trend-chart',[{label:'Requires Kusto access',value:0,display:'N/A'}],1,()=>'accent');

// Customer Intelligence table
const custTbody=document.getElementById('customer-tbody');
customers.slice(0,200).forEach(c=>{
  const tr=document.createElement('tr');tr.setAttribute('data-tier',c.tier);
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td style="font-size:11px;color:var(--cp-text-muted)">${c.tenantId||'—'}</td><td>${c.industry||'—'}</td><td>${fmt(c.seats)}</td><td>${d365EdBadge(c.d365Edition)}</td><td>${fmt(c.d365Lic)}</td><td>${m365E5Badge(c.m365E5)}</td><td>${fmt(c.copilotLic)}</td><td>${c.ownedCount}</td><td>${c.liveAgents}</td><td>${fmt(c.usedCredits)}</td><td>${scoreBubble(c.consumptionScore)}</td><td>${tierBadge(c.tier)}</td>`;
  custTbody.appendChild(tr);
});

// Consumption
makeKPIs('consumption-kpis',[
  {label:'Total',value:fmt(customers.length),delta:'All sources',deltaClass:'up'},
  {label:'Green',value:String(customers.filter(c=>c.tier==='Green').length),delta:'Active',deltaClass:'up'},
  {label:'Yellow',value:String(customers.filter(c=>c.tier==='Yellow').length),delta:'In progress',deltaClass:'flat'},
  {label:'Red',value:String(customers.filter(c=>c.tier==='Red').length),delta:'Needs work',deltaClass:'down'}
]);

const consTbody=document.getElementById('consumption-tbody');
customers.slice(0,50).forEach((c,i)=>{
  const tr=document.createElement('tr');tr.setAttribute('data-tier',c.tier);
  tr.innerHTML=`<td>${i+1}</td><td style="font-weight:600">${c.name}</td><td>${c.industry||'—'}</td><td>${fmt(c.usedCredits)}</td><td>${fmt(c.mau)}</td><td>${c.pru}%</td><td>${fmt(c.agentMAU)}</td><td>${trendArrow(c.growthTrend)}</td><td>${scoreBubble(c.consumptionScore)}</td><td>${tierBadge(c.tier)}</td>`;
  consTbody.appendChild(tr);
});

renderBarChart('agent-status-chart',[
  {label:'Live',value:customers.filter(c=>c.customerStatus==='Live').length},
  {label:'Implement',value:customers.filter(c=>c.customerStatus==='Implement').length},
  {label:'POC',value:customers.filter(c=>c.customerStatus==='POC').length},
  {label:'No Active Agents',value:customers.filter(c=>c.customerStatus==='No Active Agents').length}
],Math.max(customers.length/2,1),d=>d.label.includes('Live')?'success':d.label.includes('Implement')?'blue':d.label.includes('POC')?'warning':'danger');

const matTbody=document.getElementById('agent-matrix-tbody');
customers.filter(c=>c.ownedCount>0).slice(0,20).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${statusBadge(c.ownedAgents.Qualification)}</td><td>${statusBadge(c.ownedAgents.Opportunity)}</td><td>${statusBadge(c.ownedAgents.Development)}</td><td>${statusBadge(c.ownedAgents.Research)}</td><td>${statusBadge(c.ownedAgents.Close)}</td><td><span class="badge badge-accent">${c.ownedCount}/5</span></td>`;
  matTbody.appendChild(tr);
});

// Copilot page
makeKPIs('copilot-kpis',[
  {label:'Live',value:fmt(_kpis.live_customers),delta:'Agent Live',deltaClass:'up'},
  {label:'POC',value:fmt(_kpis.poc_customers),delta:'Proof of concept',deltaClass:'flat'},
  {label:'Deploy',value:fmt(_kpis.deploy_customers),delta:'Implementation',deltaClass:'up'},
  {label:'No Agents',value:fmt(_kpis.no_agents),delta:'Opportunity',deltaClass:'down'}
]);
renderBarChart('copilot-seats-chart',[
  {label:'Live Status',value:_kpis.live_customers},
  {label:'Implement Status',value:_kpis.deploy_customers},
  {label:'POC Status',value:_kpis.poc_customers},
  {label:'No Active Agents',value:_kpis.no_agents}
],Math.max(_kpis.no_agents,1),d=>d.label.includes('Live')?'success':d.label.includes('Implement')?'blue':d.label.includes('POC')?'warning':'danger');
renderBarChart('copilot-agent-chart',[
  {label:'With Projects + Live',value:customers.filter(c=>c.isFusion&&c.customerStatus==='Live').length},
  {label:'With Projects (not live)',value:customers.filter(c=>c.isFusion&&c.customerStatus!=='Live').length},
  {label:'No Projects',value:customers.filter(c=>!c.isFusion).length}
],Math.max(customers.length,1),d=>d.label.includes('Live')?'success':d.label.includes('not')?'warning':'danger');

const copCrossTbody=document.getElementById('copilot-crosssell-tbody');
customers.filter(c=>c.customerStatus==='No Active Agents'&&c.isFusion).slice(0,15).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>—</td><td>—</td><td>—</td><td>${c.isSales?'<span class="badge badge-green">Yes</span>':'<span class="badge badge-muted">No</span>'}</td><td><span class="badge badge-red">No Agents</span></td><td>${scoreBubble(c.wsScore)}</td>`;
  copCrossTbody.appendChild(tr);
});

// Whitespace
const wsHighCust=customers.filter(c=>c.customerStatus==='No Active Agents');
const wsDeployCust=customers.filter(c=>c.customerStatus==='Implement'||c.customerStatus==='POC');
makeKPIs('ws-kpis',[
  {label:'No Active Agents',value:String(wsHighCust.length),delta:'Full whitespace',deltaClass:'down'},
  {label:'In Deployment',value:String(wsDeployCust.length),delta:'Implement/POC',deltaClass:'flat'},
  {label:'With Projects',value:String(_kpis.with_projects),delta:'Have FT projects',deltaClass:'up'},
  {label:'Sales Focused',value:String(_kpis.sales_customers),delta:'Sales agent projects',deltaClass:'up'}
]);

document.getElementById('ws-high-count').textContent=wsHighCust.length+' accounts';
wsHighCust.slice(0,20).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${fmt(c.seats)}</td><td>${fmt(c.d365Lic)}</td><td>${c.ownedCount}</td><td>${fmt(c.usedCredits)}</td><td>${scoreBubble(c.wsScore)}</td><td><span class="badge badge-accent">${c.oppCategory}</span></td>`;
  document.getElementById('ws-high-tbody').appendChild(tr);
});

document.getElementById('ws-agent-count').textContent=wsDeployCust.length+' accounts';
wsDeployCust.slice(0,20).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>—</td><td>—</td><td>${fmt(c.agentMAU)}</td><td>—</td><td>${scoreBubble(c.wsScore)}</td>`;
  document.getElementById('ws-agent-tbody').appendChild(tr);
});

document.getElementById('ws-credit-count').textContent='0 accounts';
// Revenue model
customers.filter(c=>c.oppScore>50).sort((a,b)=>b.oppScore-a.oppScore).slice(0,20).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${fmt(c.seats)}</td><td>—</td><td><span class="badge badge-accent">${c.oppCategory}</span></td><td>${scoreBubble(c.oppScore)}</td><td>—</td>`;
  document.getElementById('ws-revenue-tbody').appendChild(tr);
});

// Fusion Community
makeKPIs('fusion-kpis',[
  {label:'Community Customers',value:String(fusionCustomers.length),delta:'With FT projects',deltaClass:'up',highlight:true},
  {label:'Live',value:String(fusionCustomers.filter(c=>c.customerStatus==='Live').length),delta:'Agent live',deltaClass:'up'},
  {label:'Deploy/Implement',value:String(fusionCustomers.filter(c=>c.fusionStage==='Active').length),delta:'Active deployment',deltaClass:'up'},
  {label:'POC',value:String(fusionCustomers.filter(c=>c.customerStatus==='POC').length),delta:'Proof of concept',deltaClass:'flat'},
  {label:'Sales Projects',value:String(fusionCustomers.filter(c=>c.isSales).length),delta:'Sales focused',deltaClass:'up'},
  {label:'No Agents',value:String(fusionCustomers.filter(c=>c.customerStatus==='No Active Agents').length),delta:'Activation needed',deltaClass:'down',highlight:true}
]);

const fOwnerTbody=document.getElementById('fusion-ownership-tbody');
document.getElementById('fusion-ownership-count').textContent=fusionCustomers.length+' customers';
fusionCustomers.forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td><span class="badge badge-blue">${c.fusionStage||'—'}</span></td><td>${d365EdBadge(c.d365Edition)}</td><td>${m365E5Badge(c.m365E5)}</td><td>${statusBadge(c.ownedAgents.Qualification)}</td><td>${statusBadge(c.ownedAgents.Research)}</td><td>${statusBadge(c.ownedAgents.Development)}</td><td>${statusBadge(c.ownedAgents.Opportunity)}</td><td>${statusBadge(c.ownedAgents.Close)}</td><td>—</td><td>${scoreBubble(c.consumptionScore)}</td><td>${scoreBubble(c.wsScore)}</td><td>${scoreBubble(c.expScore)}</td>`;
  fOwnerTbody.appendChild(tr);
});

const fConsTbody=document.getElementById('fusion-consumption-tbody');
document.getElementById('fusion-consumption-count').textContent=fusionCustomers.length+' customers';
fusionCustomers.sort((a,b)=>b.credits30d-a.credits30d).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${c.ownedCount}</td><td>${fmt(c.credits30d)}</td><td>${fmt(c.credits90d)}</td><td>${fmt(c.agentMAU)}</td><td>${trendArrow(c.growthTrend)}</td><td>${classificationBadge(c.consumptionClass)}</td>`;
  fConsTbody.appendChild(tr);
});

const fOverlayTbody=document.getElementById('fusion-overlay-tbody');
fusionCustomers.filter(c=>c.customerStatus==='No Active Agents').slice(0,20).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>—</td><td>—</td><td>${fmt(c.agentMAU)}</td><td style="font-weight:600;color:var(--cp-danger)">No agents</td><td><span class="badge badge-accent">Deploy ${c.recommendedAgent}</span></td>`;
  fOverlayTbody.appendChild(tr);
});

const fExpTbody=document.getElementById('fusion-expansion-tbody');
fusionCustomers.sort((a,b)=>b.expScore-a.expScore).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${d365EdBadge(c.d365Edition)}</td><td>${m365E5Badge(c.m365E5)}</td><td>—</td><td>${classificationBadge(c.consumptionClass)}</td><td>${fmt(c.unusedCredits)}</td><td>${c.ownedCount}/5</td><td>${fmt(c.seats)}</td><td>${scoreBubble(c.expScore)}</td><td>${expCategoryBadge(c.expCategory)}</td>`;
  fExpTbody.appendChild(tr);
});

const fNextTbody=document.getElementById('fusion-nextagent-tbody');
fusionCustomers.filter(c=>c.recommendedAgent!=='—').sort((a,b)=>b.expScore-a.expScore).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${c.currentAgents.length>0?c.currentAgents.map(a=>`<span class="badge badge-accent" style="margin:2px">${a}</span>`).join(''):'<span class="badge badge-muted">None</span>'}</td><td><span class="badge badge-blue">${c.recommendedAgent}</span></td><td style="font-size:12px;color:var(--cp-text-muted)">${c.recReason}</td><td>${scoreBubble(c.expScore)}</td>`;
  fNextTbody.appendChild(tr);
});

const fHeatTbody=document.getElementById('fusion-heatmap-tbody');
fusionCustomers.sort((a,b)=>b.expScore-a.expScore).slice(0,25).forEach(c=>{
  const hc=(level)=>{const cls=level==='Critical'?'heat-critical':level==='High'?'heat-high':level==='Medium'?'heat-medium':'heat-low';return`<td><span class="heatmap-cell ${cls}">${level}</span></td>`;};
  const wsLevel=c.wsScore>=80?'Critical':c.wsScore>=50?'High':c.wsScore>=30?'Medium':'Low';
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td><span class="badge badge-blue">${c.fusionStage||'—'}</span></td>${hc(c.consumptionClass==='None'?'Critical':c.consumptionClass==='Low'?'High':'Low')}${hc(c.customerStatus==='Live'?'Low':'High')}${hc(wsLevel)}${hc(c.expCategory)}${hc(c.expCategory)}`;
  fHeatTbody.appendChild(tr);
});

const stalledTbody=document.getElementById('heatmap-stalled-tbody');
fusionCustomers.filter(c=>c.daysStalled>30).sort((a,b)=>b.daysStalled-a.daysStalled).slice(0,25).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td><span class="badge badge-blue">${c.fusionStage||'—'}</span></td><td style="color:var(--cp-danger)">${c.daysStalled}d</td><td>${fmt(c.usedCredits)}</td>`;
  stalledTbody.appendChild(tr);
});

const heatCopTbody=document.getElementById('heatmap-copilot-tbody');
fusionCustomers.filter(c=>c.customerStatus==='No Active Agents').slice(0,25).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>—</td><td>${fmt(c.agentMAU)}</td><td>${scoreBubble(c.oppScore)}</td>`;
  heatCopTbody.appendChild(tr);
});

// Top Opportunities
makeKPIs('opp-kpis',[
  {label:'Activation',value:String(customers.filter(c=>c.oppCategory==='Activation').length),delta:'No consumption',deltaClass:'down'},
  {label:'Expansion',value:String(customers.filter(c=>c.oppCategory==='Expansion').length),delta:'Low utilization',deltaClass:'flat'},
  {label:'Cross-Sell',value:String(customers.filter(c=>c.oppCategory==='Cross-Sell').length),delta:'New product fit',deltaClass:'up'},
  {label:'Upsell',value:String(customers.filter(c=>c.oppCategory==='Upsell').length),delta:'Already active',deltaClass:'up'}
]);

customers.sort((a,b)=>b.oppScore-a.oppScore).slice(0,25).forEach((c,i)=>{
  const catCls=c.oppCategory==='Activation'?'badge-red':c.oppCategory==='Expansion'?'badge-yellow':c.oppCategory==='Cross-Sell'?'badge-blue':'badge-green';
  const tr=document.createElement('tr');
  tr.innerHTML=`<td>${i+1}</td><td style="font-weight:600">${c.name}</td><td><span class="badge ${catCls}">${c.oppCategory}</span></td><td>${fmt(c.seats)}</td><td>${5-c.liveAgents} agents</td><td>${scoreBubble(c.oppScore)}</td><td>—</td>`;
  document.getElementById('opp-top25-tbody').appendChild(tr);
});

customers.filter(c=>c.recommendedAgent!=='—').sort((a,b)=>b.oppScore-a.oppScore).slice(0,20).forEach(c=>{
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${c.currentAgents.length>0?c.currentAgents.map(a=>`<span class="badge badge-accent" style="margin:2px">${a}</span>`).join(''):'<span class="badge badge-muted">None</span>'}</td><td><span class="badge badge-blue">${c.recommendedAgent}</span></td><td style="font-size:12px;color:var(--cp-text-muted)">${c.recReason}</td><td>${scoreBubble(c.oppScore)}</td>`;
  document.getElementById('opp-next-tbody').appendChild(tr);
});

customers.filter(c=>c.growthTrend<0).sort((a,b)=>a.growthTrend-b.growthTrend).slice(0,20).forEach(c=>{
  const risk=c.growthTrend<=-10?'<span class="badge badge-red">High</span>':c.growthTrend<=-5?'<span class="badge badge-yellow">Medium</span>':'<span class="badge badge-muted">Low</span>';
  const tr=document.createElement('tr');
  tr.innerHTML=`<td style="font-weight:600">${c.name}</td><td>${fmt(c.credits30d)}</td><td>${fmt(c.credits90d)}</td><td>${trendArrow(c.growthTrend)}</td><td>${c.liveAgents}</td><td>${risk}</td>`;
  document.getElementById('opp-declining-tbody').appendChild(tr);
});

// Navigation
document.querySelectorAll('.nav-item').forEach(item=>{
  item.addEventListener('click',()=>{
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById('page-'+item.dataset.page).classList.add('active');
    window.scrollTo(0,0);
  });
});
document.querySelectorAll('.tab-btn').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const parent=btn.closest('.page');
    parent.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    parent.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-'+btn.dataset.tab).classList.add('active');
  });
});
document.getElementById('themeBtn').addEventListener('click',()=>{
  const cur=document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme',cur==='dark'?'light':'dark');
});
function filterTable(tableId,query){
  const rows=document.querySelectorAll('#'+tableId+' tbody tr');
  const q=query.toLowerCase();let vis=0;
  rows.forEach(r=>{const show=r.textContent.toLowerCase().includes(q);r.style.display=show?'':'none';if(show)vis++;});
  const countEl=document.getElementById(tableId.replace('-table','-count'));
  if(countEl)countEl.textContent=vis+' customers';
}
function filterTableByAttr(tableId,attr,val){
  const rows=document.querySelectorAll('#'+tableId+' tbody tr');let vis=0;
  rows.forEach(r=>{if(!val){r.style.display='';vis++;return;}const show=r.getAttribute(attr)===val;r.style.display=show?'':'none';if(show)vis++;});
  const countEl=document.getElementById(tableId.replace('-table','-count'));
  if(countEl)countEl.textContent=vis+' customers';
}
function filterTableByCol(tableId,colIdx,val){
  const rows=document.querySelectorAll('#'+tableId+' tbody tr');let vis=0;
  rows.forEach(r=>{if(!val){r.style.display='';vis++;return;}const cell=r.children[colIdx];const show=cell&&cell.textContent.includes(val);r.style.display=show?'':'none';if(show)vis++;});
  const countEl=document.getElementById(tableId.replace('-table','-count'));
  if(countEl)countEl.textContent=vis+' customers';
}
function copyPrompt(btn){const block=btn.parentElement;const text=block.textContent.replace('Copy','').trim();navigator.clipboard.writeText(text).then(()=>{btn.textContent='✓ Copied';setTimeout(()=>btn.textContent='Copy',1500);});}
function copyText(text){navigator.clipboard.writeText(text.trim());}
document.querySelectorAll('.step-badge').forEach(b=>{b.addEventListener('click',()=>{const el=document.getElementById(b.dataset.step);if(el)el.scrollIntoView({behavior:'smooth',block:'start'});});});
"""


if __name__ == '__main__':
    build_html()
