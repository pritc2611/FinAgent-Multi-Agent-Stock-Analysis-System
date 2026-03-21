/* FinAgent Research Terminal — script.js (Modern Pro Edition)
   ─────────────────────────────────────────────────────────────
   Updated for the new side-by-side layout and design system.
   ─────────────────────────────────────────────────────────────
*/

'use strict';

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const el = {
  query:         $('query'),
  submitBtn:     $('submitBtn'),
  submitIcon:    $('submitIcon'),
  submitLabel:   $('submitLabel'),
  stopBtn:       $('stopBtn'),
  apiBase:       $('apiBase'),
  healthLed:     $('healthLed'),
  healthTxt:     $('healthTxt'),
  streamLed:     $('streamLed'),
  streamTxt:     $('streamTxt'),
  runIdShort:    $('runIdShort'),
  pipelineTrack: $('pipelineTrack'),
  tickerHero:    $('tickerHero'),
  tickerSym:     $('tickerSym'),
  tickerCompany: $('tickerCompany'),
  tickerChat:    $('tickerChat'),
  tickerFlag:    $('tickerFlag'),
  resultEmpty:   $('resultEmpty'),
  resultFull:    $('resultFull'),
  metricsRow:    $('metricsRow'),
  historyFeed:   $('historyFeed'),
  refreshHistBtn:$('refreshHistBtn'),
  modalOverlay:  $('modalOverlay'),
  modalTicker:   $('modalTicker'),
  modalCompany:  $('modalCompany'),
  modalMetrics:  $('modalMetrics'),
  modalClose:    $('modalClose'),
};

// ── State ─────────────────────────────────────────────────────────────────────
let currentRunId   = null;
let source         = null;
const resultCache  = {};
const STORAGE_KEY  = 'finagent.apiBase';

// ── Pipeline node definitions ─────────────────────────────────────────────────
const NODES = [
  { id: 'chat_node',       label: 'Chat Processor',    tip: 'Extracting ticker symbol',  icon: '💬' },
  { id: 'market_data',     label: 'Market Intelligence',tip: 'Live financial metrics',     icon: '📊' },
  { id: 'search',          label: 'Search Sentinel',   tip: 'News & Sentiment analysis',  icon: '🔍' },
  { id: 'analyst',         label: 'Equity Analyst',    tip: 'Risk & Value assessment',    icon: '🧠' },
  { id: 'risk_mitigation', label: 'Risk Mitigation',   tip: 'Hedging & Strategy',         icon: '🛡️' },
  { id: 'reporter',        label: 'Lead Reporter',     tip: 'Compiling Final Brief',      icon: '📄' },
];

/**
 * Initialize the side-by-side layout
 */
function init() {
  buildPipeline();
  checkHealth();
  refreshHistory();
  
  // Set default API base if empty
  el.apiBase.value = localStorage.getItem(STORAGE_KEY) || '';
  el.apiBase.addEventListener('change', () => {
    localStorage.setItem(STORAGE_KEY, el.apiBase.value.trim());
    checkHealth();
  });
}

// ── Pipeline build & control ──────────────────────────────────────────────────
function buildPipeline() {
  el.pipelineTrack.innerHTML = '';
  NODES.forEach((node) => {
    const item = document.createElement('div');
    item.className = 'node-item';
    item.id = `node-${node.id}`;
    item.innerHTML = `
      <div class="node-icon">${node.icon}</div>
      <div class="node-info">
        <div class="node-label">${node.label}</div>
        <div class="node-desc">${node.tip}</div>
      </div>
      <div class="node-status" id="status-${node.id}">Awaiting...</div>
    `;
    el.pipelineTrack.appendChild(item);
  });
}

function setNodeState(nodeId, state) {
  const nodeEl = $(`node-${nodeId}`);
  const statusEl = $(`status-${nodeId}`);
  if (!nodeEl) return;

  if (state === 'running') {
    nodeEl.className = 'node-item active';
    statusEl.textContent = 'RUNNING';
  } else if (state === 'done') {
    nodeEl.className = 'node-item done';
    statusEl.textContent = 'COMPLETE';
  } else {
    nodeEl.className = 'node-item';
    statusEl.textContent = 'PENDING';
  }
}

function clearPipeline() {
  NODES.forEach(n => setNodeState(n.id, 'idle'));
}

// ── API Helpers ───────────────────────────────────────────────────────────────
function getBase() {
  return (el.apiBase.value || '').trim().replace(/\/$/, '');
}

async function apiReq(path, opts = {}) {
  const url = getBase() + path;
  const res = await fetch(url, {
    ...opts, 
    headers: { 'Content-Type': 'application/json', ...(opts.headers||{}) },
  });
  if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`);
  return res.status === 204 ? null : res.json();
}

async function checkHealth() {
  try {
    const d = await apiReq('/health');
    el.healthLed.className = d.status === 'healthy' ? 'status-led ok' : 'status-led warn';
    el.healthTxt.textContent = d.status === 'healthy' ? 'ONLINE' : 'UNCERTAIN';
  } catch {
    el.healthLed.className = 'status-led bad';
    el.healthTxt.textContent = 'OFFLINE';
  }
}

// ── Stream Logic ──────────────────────────────────────────────────────────────
function openStream(runId) {
  closeStream();
  source = new EventSource(getBase() + `/api/v1/stream/${runId}`);
  setStreamState('warn', 'LIVE');

  source.addEventListener('ticker', e => {
    const d = JSON.parse(e.data);
    showTicker(d.ticker, d.company_name, d.chat_response);
    setNodeState('chat_node', 'done');
  });

  source.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    setNodeState(d.node, 'running');
  });

  source.addEventListener('complete', e => {
    const d = JSON.parse(e.data);
    NODES.forEach(n => setNodeState(n.id, 'done'));
    renderResult(d);
    closeStream('done');
    refreshHistory();
  });

  source.addEventListener('error', async () => {
    // Fallback polling check
    try {
      if (currentRunId) {
        const s = await apiReq(`/api/v1/status/${currentRunId}`);
        if (s.status === 'completed') {
           const r = await apiReq(`/api/v1/result/${currentRunId}`);
           renderResult(r);
           refreshHistory();
           closeStream('done');
           return;
        }
      }
    } catch (_) {}
    closeStream('error');
  });
}

function closeStream(outcome) {
  if (source) { source.close(); source = null; }
  setLoading(false);
  setStreamState(outcome === 'done' ? 'ok' : (outcome ? 'bad' : 'neutral'), outcome ? (outcome === 'done' ? 'FINISHED' : 'ERROR') : 'IDLE');
}

function setStreamState(state, txt) {
  el.streamLed.className = `status-led ${state}`;
  el.streamTxt.textContent = txt;
}

// ── UI Control ────────────────────────────────────────────────────────────────
function setLoading(on) {
  el.submitBtn.disabled = on;
  el.stopBtn.disabled   = !on;
  el.submitLabel.textContent = on ? 'ANALYZING...' : 'RUN ANALYSIS';
  if (on) {
    el.resultEmpty.style.display = 'flex';
    el.resultFull.style.display  = 'none';
  }
}

function showTicker(sym, company, chat, risk) {
  el.resultEmpty.style.display = 'none';
  el.resultFull.style.display  = 'flex';
  
  el.tickerSym.textContent = sym || '??';
  el.tickerCompany.textContent = company || '';
  el.tickerChat.textContent = chat || '';
  
  if (risk !== undefined) {
    el.tickerFlag.textContent = risk ? 'HIGH RISK' : 'LOW RISK';
    el.tickerFlag.style.backgroundColor = risk ? 'var(--danger)' : 'var(--success)';
    el.tickerFlag.style.color = '#fff';
    el.tickerFlag.className = 'hist-status';
  } else {
    el.tickerFlag.textContent = 'PENDING';
    el.tickerFlag.style.backgroundColor = 'var(--bg-card-alt)';
    el.tickerFlag.style.color = 'var(--text-muted)';
  }
}

function formatCurrency(value, currency = "USD") {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency,
  }).format(value);
}

function renderMetrics(data, container) {
  const fd = data.financial_data || {};
  container.innerHTML = `
    <div class="metric-box"><div class="m-label">Price</div><div class="m-value">${formatCurrency(fd.price, fd.currency) || '—'}</div></div>
    <div class="metric-box"><div class="m-label">P/E Ratio</div><div class="m-value">${fd.pe_ratio || '—'}</div></div>
    <div class="metric-box"><div class="m-label">Sentiment</div><div class="m-value ${data.sentiment_score > 0 ? 'text-success' : 'text-danger'}">${data.sentiment_score ? (data.sentiment_score > 0 ? 'Bullish' : 'Bearish') : 'Neutral'}</div></div>
  `;
}

function renderResult(data) {
  resultCache[data.run_id] = data;
  showTicker(data.ticker, data.company_name, data.chat_response, data.risk_flag);
  renderMetrics(data, el.metricsRow);
  populateTabs(data, 'main');
}

function populateTabs(data, target) {
  const suffix = target === 'main' ? '' : 'm';
  const prefix = target === 'main' ? 'tab-' : '';
  
  $(prefix + suffix + 'memo').innerHTML = mdToHtml(data.investment_memo || 'Preparing report...');
  $(prefix + suffix + 'risk').innerHTML = mdToHtml(`## Risk Assessment\n\n${data.analyst_rationale || 'Calculating results...'}`);
  $(prefix + suffix + 'hedge').innerHTML = mdToHtml(`## Hedge Strategies\n\n${data.hedging_strategies || 'Analyzing exposure...'}`);
  
  const newsH = $(prefix + suffix + 'news');
  newsH.innerHTML = '<h2>Recent News</h2>';
  if (data.news_headlines && data.news_headlines.length) {
    data.news_headlines.forEach(h => {
      const div = document.createElement('div');
      div.className = 'node-item';
      div.style.marginBottom = '0.5rem';
      div.innerHTML = `<div class="node-info"><div class="node-label">${h}</div></div>`;
      newsH.appendChild(div);
    });
  } else {
    newsH.innerHTML += '<p>No recent news found.</p>';
  }
}

// ── Tab Listeners ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const parent = btn.parentElement;
    const tabName = btn.dataset.tab || btn.dataset.mtab;
    const isModal = !!btn.dataset.mtab;
    
    parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    const panelId = isModal ? tabName : `tab-${tabName}`;
    const panels = isModal ? $('modalOverlay').querySelectorAll('.tab-panel') : el.resultFull.querySelectorAll('.tab-panel');
    
    panels.forEach(p => p.classList.remove('active'));
    $(panelId).classList.add('active');
  });
});

// ── History ───────────────────────────────────────────────────────────────────
async function refreshHistory() {
  try {
    const jobs = await apiReq('/api/v1/jobs');
    el.historyFeed.innerHTML = '';
    if (!jobs || !jobs.length) {
      el.historyFeed.innerHTML = '<div class="log-empty">No history.</div>';
      return;
    }
    
    jobs.forEach(job => {
      const item = document.createElement('div');
      item.className = 'hist-item';
      if (job.run_id === currentRunId) item.classList.add('active');
      
      const sent = resultCache[job.run_id]?.sentiment_score;
      const sentColor = sent > 0 ? 'text-success' : (sent < 0 ? 'text-danger' : 'text-muted');
      
      item.innerHTML = `
        <div class="hist-top">
          <span class="hist-ticker">${job.ticker || '???'}</span>
          <span class="hist-status ${job.status}">${job.status}</span>
        </div>
        <div class="hist-query">${job.user_query}</div>
      `;
      item.onclick = () => openModal(job.run_id);
      el.historyFeed.appendChild(item);
    });
  } catch (e) {
    el.historyFeed.innerHTML = '<div class="log-empty">Connection error.</div>';
  }
}

async function openModal(runId) {
  let data = resultCache[runId];
  if (!data) {
    try {
      data = await apiReq(`/api/v1/result/${runId}`);
      resultCache[runId] = data;
    } catch { return; }
  }
  
  el.modalTicker.textContent = data.ticker || '??';
  el.modalCompany.textContent = data.company_name || '';
  renderMetrics(data, el.modalMetrics);
  populateTabs(data, 'modal');
  
  el.modalOverlay.classList.remove('hidden');
}

el.modalClose.onclick = () => el.modalOverlay.classList.add('hidden');

// ── Submission ────────────────────────────────────────────────────────────────
el.submitBtn.onclick = async () => {
  const query = el.query.value.trim();
  if (!query) return;
  
  setLoading(true);
  clearPipeline();
  el.runIdShort.textContent = '...';
  
  try {
    const res = await apiReq('/api/v1/analyse', {
      method: 'POST',
      body: JSON.stringify({ query })
    });
    currentRunId = res.run_id;
    el.runIdShort.textContent = res.run_id.slice(0, 8);
    openStream(res.run_id);
  } catch (e) {
    alert('Error starting analysis: ' + e.message);
    setLoading(false);
  }
};

el.stopBtn.onclick = () => closeStream('user stop');
el.refreshHistBtn.onclick = () => refreshHistory();

// ── Markdown Helper ──────────────────────────────────────────────────────────
function mdToHtml(md) {
  if (!md) return '';

  let html = md.trim();

  // 1. Horizontal Rules
  html = html.replace(/^---$/gm, '<hr>');

  // 2. Tables
  const lines = html.split('\n');
  const processedLines = [];
  let inTable = false;
  let tableRows = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) inTable = true;
      if (line.includes('---')) continue;
      
      const cells = line.split('|').filter(c => c.length > 0).map(c => c.trim());
      const tag = tableRows.length === 0 ? 'th' : 'td';
      const row = `<tr>${cells.map(c => `<${tag}>${c}</${tag}>`).join('')}</tr>`;
      tableRows.push(row);
    } else {
      if (inTable) {
        processedLines.push(`<div class="table-wrap"><table>${tableRows.join('')}</table></div>`);
        tableRows = [];
        inTable = false;
      }
      processedLines.push(lines[i]);
    }
  }
  if (inTable) processedLines.push(`<div class="table-wrap"><table>${tableRows.join('')}</table></div>`);
  html = processedLines.join('\n');

  // 3. Headers
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');

  // 4. Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // 5. Lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gms, '<ul>$1</ul>');

  // 6. Paragraphs
  const blocks = html.split(/\n\n+/);
  html = blocks.map(block => {
    const trimmed = block.trim();
    if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<div class="table-wrap"') || trimmed.startsWith('<hr')) {
      return trimmed;
    }
    return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');

  return html;
}

// ── Initialize ────────────────────────────────────────────────────────────────
init();