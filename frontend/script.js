/* FinAgent Console — Premium UI Script
   Connects to FastAPI backend via REST + SSE streaming
   ─────────────────────────────────────────────────── */

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const els = {
  form:           $('analysisForm'),
  query:          $('query'),
  submitBtn:      $('submitBtn'),
  stopBtn:        $('stopBtn'),
  apiBase:        $('apiBase'),
  healthDot:      $('healthDot'),
  healthLabel:    $('healthLabel'),
  streamDot:      $('streamDot'),
  streamLabel:    $('streamLabel'),
  nodeCount:      $('nodeCount'),
  completedCount: $('completedCount'),
  runIdShort:     $('runIdShort'),
  // Analysis panel
  tickerBadgeWrap:$('tickerBadgeWrap'),
  tickerSym:      $('tickerSym'),
  tickerName:     $('tickerName'),
  chatBar:        $('chatBar'),
  chatText:       $('chatText'),
  resultEmpty:    $('resultEmpty'),
  resultContent:  $('resultContent'),
  metricsStrip:   $('metricsStrip'),
  // Pipeline panel
  pipelineNodes:  $('pipelineNodes'),
  progressLog:    $('progressLog'),
  streamStateTag: $('streamStateTag'),
  // History panel
  jobsList:       $('jobsList'),
  refreshJobsBtn: $('refreshJobsBtn'),
};

// ── State ────────────────────────────────────────────────────────────────────
let currentRunId   = null;
let source         = null;
let completedRuns  = 0;
let observedNodes  = new Set();

const STORAGE_KEY = 'finagent.apiBase';
els.apiBase.value  = localStorage.getItem(STORAGE_KEY) || '';

// ── Pipeline node definitions ─────────────────────────────────────────────────
const PIPELINE_NODES = [
  { id: 'chat_node',        label: 'Chat',      icon: chatIcon() },
  { id: 'market_data',      label: 'Market',    icon: chartIcon() },
  { id: 'search',           label: 'Search',    icon: searchIcon() },
  { id: 'analyst',          label: 'Analyst',   icon: brainIcon() },
  { id: 'risk_mitigation',  label: 'Risk',      icon: shieldIcon() },
  { id: 'reporter',         label: 'Reporter',  icon: docIcon() },
];

// ── API helpers ───────────────────────────────────────────────────────────────
function apiBase() {
  const manual = (els.apiBase.value || '').trim().replace(/\/$/, '');
  return manual || 'http://localhost:8000';
}

function endpoint(path) { return `${apiBase()}${path}`; }

async function apiRequest(path, opts = {}) {
  const res = await fetch(endpoint(path), {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

// ── Panel routing ─────────────────────────────────────────────────────────────
function switchPanel(name) {
  ['analysis', 'pipeline', 'history'].forEach(p => {
    $(`panel-${p}`).style.display = p === name ? '' : 'none';
  });
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.panel === name);
  });
  if (name === 'history') refreshJobs();
}

document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => switchPanel(btn.dataset.panel));
});

// ── Health check ──────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const data = await apiRequest('/health');
    const ok = data.status === 'healthy';
    setHealth(ok ? 'ok' : 'warn', ok ? 'Backend connected' : 'Backend uncertain');
  } catch {
    setHealth('bad', 'Backend unreachable');
  }
}

function setHealth(state, label) {
  els.healthDot.className = `status-dot ${state}`;
  els.healthLabel.textContent = label;
}

function setStream(state, label) {
  els.streamDot.className = `status-dot ${state}`;
  els.streamLabel.textContent = label;
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function updateStats() {
  els.nodeCount.textContent      = String(observedNodes.size);
  els.completedCount.textContent = String(completedRuns);
  els.runIdShort.textContent     = currentRunId ? currentRunId.slice(0, 6) : '—';
}

// ── Pipeline visual ───────────────────────────────────────────────────────────
function buildPipelineVisual() {
  els.pipelineNodes.innerHTML = '';
  PIPELINE_NODES.forEach((node, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'pipe-node';
    wrap.id = `pipe-${node.id}`;
    wrap.innerHTML = `
      <div class="pipe-node-circle">${node.icon}</div>
      <span class="pipe-node-label">${node.label}</span>
    `;
    els.pipelineNodes.appendChild(wrap);

    if (i < PIPELINE_NODES.length - 1) {
      const conn = document.createElement('div');
      conn.className = 'pipe-connector';
      conn.id = `conn-${i}`;
      els.pipelineNodes.appendChild(conn);
    }
  });
}

function setPipelineNodeState(nodeId, state) {
  // state: 'running' | 'done'
  PIPELINE_NODES.forEach((n, i) => {
    const el = $(`pipe-${n.id}`);
    if (!el) return;
    if (n.id === nodeId) {
      el.className = `pipe-node ${state}`;
    } else if (state === 'running' && i < PIPELINE_NODES.findIndex(x => x.id === nodeId)) {
      el.className = 'pipe-node done';
    }
  });

  // Activate connectors up to current
  const idx = PIPELINE_NODES.findIndex(n => n.id === nodeId);
  for (let i = 0; i < idx; i++) {
    const conn = $(`conn-${i}`);
    if (conn) conn.classList.add('active');
  }
}

// ── Progress log ──────────────────────────────────────────────────────────────
function resetProgressLog() {
  els.progressLog.innerHTML = '';
}

function appendLog(node, status, message) {
  // Remove empty state
  const empty = els.progressLog.querySelector('.log-empty');
  if (empty) empty.remove();

  const now  = new Date();
  const time = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;

  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-node">${escHtml(node)}</span>
    <span class="log-msg">${escHtml(message || nodeLabel(node))}</span>
    <span class="log-status"><span class="log-pill ${status}">${status}</span></span>
  `;
  els.progressLog.appendChild(entry);
  els.progressLog.scrollTop = els.progressLog.scrollHeight;
}

function nodeLabel(nodeId) {
  const labels = {
    chat_node:       'Extracting ticker from query',
    market_data:     'Fetching live market data',
    search:          'Searching news & scoring sentiment',
    analyst:         'Running risk & valuation analysis',
    risk_mitigation: 'Researching hedging strategies',
    reporter:        'Compiling investment brief',
  };
  return labels[nodeId] || nodeId;
}

// ── Stream state tag ──────────────────────────────────────────────────────────
function setStreamTag(text, cls) {
  els.streamStateTag.textContent = text;
  els.streamStateTag.className = `stream-state-tag ${cls || ''}`;
}

// ── Loading state ─────────────────────────────────────────────────────────────
function setLoading(on) {
  els.submitBtn.disabled = on;
  els.stopBtn.disabled   = !on;
  if (on) {
    els.submitBtn.innerHTML = `
      <span style="display:flex;gap:3px;align-items:center">
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
        <span class="thinking-dot"></span>
      </span>`;
  } else {
    els.submitBtn.innerHTML = `Run Analysis <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
  }
}

// ── Ticker badge ──────────────────────────────────────────────────────────────
function showTicker(sym, name, chatMsg) {
  els.tickerSym.textContent  = sym || '—';
  els.tickerName.textContent = name || '';
  els.tickerBadgeWrap.style.display = '';

  if (chatMsg) {
    els.chatText.textContent = chatMsg;
    els.chatBar.style.display = 'flex';
  }
}

// ── Metrics strip ─────────────────────────────────────────────────────────────
function renderMetrics(data) {
  const fd = data.financial_data || {};
  const sentiment = data.sentiment_score;
  const sentClass = sentiment > 0.1 ? 'ok' : sentiment < -0.1 ? 'danger' : '';
  const sentLabel = sentiment > 0.1 ? 'Bullish' : sentiment < -0.1 ? 'Bearish' : 'Neutral';
  const riskClass = data.risk_flag ? 'danger' : 'ok';

  els.metricsStrip.innerHTML = `
    ${metricCell('Price', fd.price != null ? `$${fd.price}` : '—', '')}
    ${metricCell('P/E Ratio', fd.pe_ratio ?? '—', '')}
    ${metricCell('52W High', fd.week52_high != null ? `$${fd.week52_high}` : '—', '')}
    ${metricCell('52W Low',  fd.week52_low  != null ? `$${fd.week52_low}`  : '—', '')}
    ${metricCell('Sentiment', sentLabel, sentClass)}
    ${metricCell('Risk Level', data.risk_flag ? 'HIGH' : 'STANDARD', riskClass)}
  `;
}

function metricCell(label, value, cls) {
  return `<div class="metric-cell">
    <p class="label">${escHtml(label)}</p>
    <p class="value ${cls}">${escHtml(String(value))}</p>
  </div>`;
}

// ── Result rendering ──────────────────────────────────────────────────────────
function renderResult(data) {
  els.resultEmpty.style.display   = 'none';
  els.resultContent.style.display = '';

  renderMetrics(data);

  // Investment memo (render markdown-ish)
  $('tab-memo').innerHTML = renderMarkdown(data.investment_memo || 'No memo generated.');

  // Risk rationale
  $('tab-rationale').innerHTML = `
    <div style="display:flex;align-items:center;gap:.6rem;margin-bottom:1rem">
      <span class="risk-badge ${data.risk_flag ? 'high' : 'low'}">
        ${data.risk_flag ? '▲ HIGH RISK' : '✓ STANDARD RISK'}
      </span>
    </div>
    <div class="memo-body">${escHtml(data.analyst_rationale || 'No rationale available.')}</div>
  `;

  // Hedging
  $('tab-hedging').innerHTML = `<div class="memo-body">${escHtml(data.hedging_strategies || 'No elevated risk — no hedging strategies required.')}</div>`;

  // Headlines
  const headlines = data.news_headlines || [];
  $('tab-news').innerHTML = headlines.length
    ? `<ul class="headline-list">${headlines.map(h => `<li class="headline-item">${escHtml(h)}</li>`).join('')}</ul>`
    : `<p style="color:var(--text-3);font-size:.82rem">No headlines retrieved.</p>`;
}

// Simple markdown → HTML
function renderMarkdown(md) {
  return md
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^  • (.+)$/gm, '<li>$1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hup])/gm, '')
    .replace(/\n/g, ' ')
    .trim();
}

// ── Result tab switching ──────────────────────────────────────────────────────
document.querySelectorAll('.rtab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.rtab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.result-tab-content').forEach(c => c.style.display = 'none');
    tab.classList.add('active');
    $(`tab-${tab.dataset.tab}`).style.display = '';
  });
});

// ── Stream management ─────────────────────────────────────────────────────────
function openStream(runId) {
  closeStream();
  source = new EventSource(endpoint(`/api/v1/stream/${runId}`));
  setStream('warn', 'Streaming…');
  setStreamTag('Live', 'active');
  switchPanel('pipeline');

  source.addEventListener('ticker', e => {
    const d = JSON.parse(e.data);
    showTicker(d.ticker, d.company_name, d.chat_response);
    // Auto-switch back to analysis after ticker comes in
    setTimeout(() => switchPanel('analysis'), 600);
  });

  source.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    observedNodes.add(d.node);
    updateStats();
    setPipelineNodeState(d.node, 'running');
    appendLog(d.node, 'running', d.message || nodeLabel(d.node));
  });

  source.addEventListener('complete', e => {
    const d = JSON.parse(e.data);
    // Mark reporter done
    setPipelineNodeState('reporter', 'done');
    appendLog('reporter', 'done', 'Investment brief compiled');
    renderResult(d);
    completedRuns++;
    updateStats();
    closeStream('done');
    refreshJobs();
    setStreamTag('Complete', 'done');
    switchPanel('analysis');
  });

  source.addEventListener('error', async () => {
    try {
      if (currentRunId) {
        const status = await apiRequest(`/api/v1/status/${currentRunId}`);
        if (status.status === 'completed') {
          const result = await apiRequest(`/api/v1/result/${currentRunId}`);
          renderResult(result);
          completedRuns++;
          updateStats();
          appendLog('fallback', 'done', 'Recovered via polling after disconnect');
          closeStream('done');
          setStreamTag('Complete', 'done');
          switchPanel('analysis');
        } else {
          closeStream();
          setStreamTag('Interrupted', '');
        }
      }
    } catch {
      closeStream();
      setStreamTag('Error', '');
    }
    refreshJobs();
  });
}

function closeStream(outcome) {
  if (source) { source.close(); source = null; }
  setLoading(false);
  if (outcome === 'done') {
    setStream('ok', 'Stream complete');
  } else {
    setStream('neutral', 'Stream idle');
  }
}

// ── Form submit ───────────────────────────────────────────────────────────────
els.form.addEventListener('submit', async e => {
  e.preventDefault();
  const query = els.query.value.trim();
  if (!query) return;

  // Reset UI
  observedNodes.clear();
  updateStats();
  els.resultEmpty.style.display   = '';
  els.resultContent.style.display = 'none';
  els.chatBar.style.display       = 'none';
  els.tickerBadgeWrap.style.display = 'none';
  resetProgressLog();
  buildPipelineVisual();
  setStreamTag('Starting…', 'active');
  setLoading(true);
  setStream('warn', 'Starting…');

  try {
    const start    = await apiRequest('/api/v1/analyse', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
    currentRunId   = start.run_id;
    updateStats();
    appendLog('api', 'running', 'Analysis accepted by backend');
    openStream(currentRunId);
  } catch (err) {
    setLoading(false);
    setStream('bad', 'Failed to start');
    setStreamTag('Error', '');
    appendLog('api', 'error', `Failed: ${err.message}`);
  }
});

els.stopBtn.addEventListener('click', () => {
  closeStream();
  setStreamTag('Stopped', '');
  appendLog('user', 'error', 'Stream stopped by user');
});

// ── History / Jobs ────────────────────────────────────────────────────────────
async function refreshJobs() {
  try {
    const jobs = await apiRequest('/api/v1/jobs');
    if (!Array.isArray(jobs) || jobs.length === 0) {
      els.jobsList.innerHTML = '<p class="history-empty">No jobs yet.</p>';
      return;
    }
    completedRuns = Math.max(completedRuns, jobs.filter(j => j.status === 'completed').length);
    updateStats();

    els.jobsList.innerHTML = jobs.slice(0, 20).map(job => `
      <div class="job-card">
        <span class="job-ticker">${escHtml(job.ticker || '??')}</span>
        <span class="job-query">${escHtml(job.user_query || 'Untitled')}</span>
        <div class="job-meta">
          <span class="status-pill ${job.status || ''}">${job.status || 'unknown'}</span>
        </div>
      </div>
    `).join('');
  } catch (err) {
    els.jobsList.innerHTML = `<p class="history-empty">Unable to load: ${escHtml(err.message)}</p>`;
  }
}

els.refreshJobsBtn.addEventListener('click', refreshJobs);

els.apiBase.addEventListener('change', () => {
  localStorage.setItem(STORAGE_KEY, els.apiBase.value.trim());
  checkHealth();
});

// ── Utility ───────────────────────────────────────────────────────────────────
function escHtml(t) {
  return String(t || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

// ── SVG icons ─────────────────────────────────────────────────────────────────
function chatIcon()   { return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`; }
function chartIcon()  { return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`; }
function searchIcon() { return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`; }
function brainIcon()  { return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-1.14"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-1.14"/></svg>`; }
function shieldIcon() { return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`; }
function docIcon()    { return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`; }

// ── Init ──────────────────────────────────────────────────────────────────────
buildPipelineVisual();
checkHealth();
refreshJobs();
updateStats();