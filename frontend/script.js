/* FinAgent Research Terminal — script.js
   ─────────────────────────────────────────────────────────────
   Same-origin by default (HF Space: FastAPI serves frontend).
   Manual override available via Connection input.
   ─────────────────────────────────────────────────────────────
*/

'use strict';

// ── Particle canvas background ────────────────────────────────────────────────
(function initCanvas() {
  const canvas = document.getElementById('bgCanvas');
  const ctx    = canvas.getContext('2d');
  let W, H, particles = [];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function mkParticle() {
    return {
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.2 + 0.3,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      alpha: Math.random() * 0.5 + 0.1,
    };
  }

  function init() {
    resize();
    particles = Array.from({length: 120}, mkParticle);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0,200,255,${p.alpha})`;
      ctx.fill();
    }
    // draw faint connecting lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist < 90) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(0,200,255,${0.06 * (1 - dist/90)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  init(); draw();
})();

// ── Clock ─────────────────────────────────────────────────────────────────────
function tickClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    [now.getHours(), now.getMinutes(), now.getSeconds()]
      .map(n => String(n).padStart(2, '0')).join(':');
}
setInterval(tickClock, 1000); tickClock();

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const el = {
  form:          $('analysisForm') || document.querySelector('form'),
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
  nodeCount:     $('nodeCount'),
  completedCount:$('completedCount'),
  runIdShort:    $('runIdShort'),
  durationVal:   $('durationVal'),
  pipelineTrack: $('pipelineTrack'),
  pipelineLog:   $('pipelineLog'),
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
let completedRuns  = 0;
let observedNodes  = new Set();
let startTime      = null;
let durationTimer  = null;
// Cache for history modal: runId → result data
const resultCache  = {};

const STORAGE_KEY  = 'finagent.apiBase';
el.apiBase.value   = localStorage.getItem(STORAGE_KEY) || '';
el.apiBase.addEventListener('change', () => {
  localStorage.setItem(STORAGE_KEY, el.apiBase.value.trim());
  checkHealth();
});

// ── Pipeline node definitions ─────────────────────────────────────────────────
const NODES = [
  { id: 'chat_node',       label: 'CHAT',    tip: 'Extracting ticker',         icon: iconChat()    },
  { id: 'market_data',     label: 'MARKET',  tip: 'Fetching live prices',      icon: iconChart()   },
  { id: 'search',          label: 'SEARCH',  tip: 'News & sentiment scan',     icon: iconSearch()  },
  { id: 'analyst',         label: 'ANALYST', tip: 'Risk assessment',           icon: iconBrain()   },
  { id: 'risk_mitigation', label: 'RISK',    tip: 'Hedging strategies',        icon: iconShield()  },
  { id: 'reporter',        label: 'REPORT',  tip: 'Compiling investment brief',icon: iconDoc()     },
];

// ── URL helpers ───────────────────────────────────────────────────────────────
function apiBase() {
  return (el.apiBase.value || localStorage.getItem(STORAGE_KEY) || '').trim().replace(/\/$/, '');
}
function endpoint(path) {
  const b = apiBase(); return b ? `${b}${path}` : path;
}
async function apiReq(path, opts = {}) {
  const res = await fetch(endpoint(path), {
    ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers||{}) },
  });
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
  return res.status === 204 ? null : res.json();
}

// ── Health ────────────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const d = await apiReq('/health');
    setHealth(d.status === 'healthy' ? 'ok' : 'warn', d.status === 'healthy' ? 'ONLINE' : 'UNCERTAIN');
  } catch {
    setHealth('bad', 'OFFLINE');
  }
}
function setHealth(state, txt) {
  el.healthLed.className = `status-led ${state}`;
  el.healthTxt.textContent = txt;
}
function setStreamState(state, txt) {
  el.streamLed.className = `status-led ${state}`;
  el.streamTxt.textContent = txt;
}

// ── Stats ─────────────────────────────────────────────────────────────────────
function updateStats() {
  el.nodeCount.textContent      = String(observedNodes.size);
  el.completedCount.textContent = String(completedRuns);
  el.runIdShort.textContent     = currentRunId ? currentRunId.slice(0, 8) + '…' : '—';
}

function startDurationTimer() {
  startTime = Date.now();
  clearInterval(durationTimer);
  durationTimer = setInterval(() => {
    const s = ((Date.now() - startTime) / 1000).toFixed(1);
    el.durationVal.textContent = `${s}s`;
  }, 100);
}
function stopDurationTimer() {
  clearInterval(durationTimer);
}

// ── Pipeline build & control ──────────────────────────────────────────────────
function buildPipeline() {
  el.pipelineTrack.innerHTML = '';
  NODES.forEach((node, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'pipe-node';
    wrap.id        = `pn-${node.id}`;
    wrap.title     = node.tip;
    wrap.innerHTML = `
      <div class="pipe-node-body">${node.icon}</div>
      <span class="pipe-node-label">${node.label}</span>
      <span class="pipe-node-status" id="ps-${node.id}">—</span>
    `;
    el.pipelineTrack.appendChild(wrap);
    if (i < NODES.length - 1) {
      const conn = document.createElement('div');
      conn.className = 'pipe-connector';
      conn.id        = `pc-${i}`;
      el.pipelineTrack.appendChild(conn);
    }
  });
}

function setPipeState(nodeId, state) {
  // state: 'running' | 'done'
  const nodeEl = $(`pn-${nodeId}`);
  const statusEl = $(`ps-${nodeId}`);
  if (!nodeEl) return;
  nodeEl.className = `pipe-node ${state}`;
  statusEl.textContent = state === 'running' ? 'ACTIVE' : 'DONE';

  const idx = NODES.findIndex(n => n.id === nodeId);
  // Mark previous nodes done, activate connectors
  NODES.forEach((n, i) => {
    if (i < idx) {
      const prev = $(`pn-${n.id}`);
      if (prev && !prev.classList.contains('done')) prev.className = 'pipe-node done';
    }
    const conn = $(`pc-${i}`);
    if (!conn) return;
    if (i < idx) { conn.className = 'pipe-connector active'; }
    else if (i === idx) { conn.className = 'pipe-connector running'; }
  });
}

function clearPipeline() {
  NODES.forEach(n => {
    const nEl = $(`pn-${n.id}`);
    const sEl = $(`ps-${n.id}`);
    if (nEl) nEl.className = 'pipe-node';
    if (sEl) sEl.textContent = '—';
  });
  for (let i = 0; i < NODES.length - 1; i++) {
    const c = $(`pc-${i}`);
    if (c) c.className = 'pipe-connector';
  }
}

// ── Pipeline log ──────────────────────────────────────────────────────────────
function resetLog() {
  el.pipelineLog.innerHTML = '<div class="log-empty">Pipeline activated…</div>';
}

function appendLog(node, status, msg) {
  const empty = el.pipelineLog.querySelector('.log-empty');
  if (empty) empty.remove();

  const now = new Date();
  const t   = [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map(n => String(n).padStart(2,'0')).join(':');

  const row = document.createElement('div');
  row.className = 'log-entry';
  row.innerHTML = `
    <span class="log-time">${t}</span>
    <span class="log-msg"><strong>${esc(node)}</strong> — ${esc(msg)}</span>
    <span class="log-pill ${status}">${status.toUpperCase()}</span>
  `;
  el.pipelineLog.appendChild(row);
  el.pipelineLog.scrollTop = el.pipelineLog.scrollHeight;
}

const NODE_MSGS = {
  chat_node:       'Extracting ticker symbol from query',
  market_data:     'Fetching live price, P/E & 52W range',
  search:          'Searching news & scoring sentiment',
  analyst:         'Running risk & fair-value assessment',
  risk_mitigation: 'Researching hedging strategies',
  reporter:        'Compiling investment brief',
};

// ── Loading state ─────────────────────────────────────────────────────────────
function setLoading(on) {
  el.submitBtn.disabled = on;
  el.stopBtn.disabled   = !on;
  el.submitBtn.classList.toggle('running', on);
  el.submitIcon.textContent  = on ? '◈' : '▶';
  el.submitLabel.textContent = on ? 'ANALYZING…' : 'RUN ANALYSIS';
}

// ── Ticker hero ───────────────────────────────────────────────────────────────
function showTicker(sym, company, chat, riskFlag) {
  el.tickerSym.textContent     = sym || '??';
  el.tickerCompany.textContent = company || '';
  el.tickerChat.textContent    = chat || '';
  if (riskFlag !== undefined) {
    el.tickerFlag.textContent  = riskFlag ? '▲ HIGH RISK' : '✓ STD RISK';
    el.tickerFlag.className    = `ticker-flag ${riskFlag ? 'high' : 'low'}`;
  } else {
    el.tickerFlag.textContent  = '';
  }
  el.tickerHero.style.display = '';
}

// ── Metrics ───────────────────────────────────────────────────────────────────
function renderMetrics(data, container) {
  const fd  = data.financial_data || {};
  const s   = data.sentiment_score;
  const sl  = s > 0.1 ? 'ok' : s < -0.1 ? 'danger' : '';
  const slb = s > 0.1 ? 'BULLISH' : s < -0.1 ? 'BEARISH' : 'NEUTRAL';
  const rl  = data.risk_flag ? 'danger' : 'ok';
  container.innerHTML = [
    mc('PRICE',     fd.price     != null ? `$${fd.price}`    : '—',  ''),
    mc('P/E',       fd.pe_ratio  != null ? fd.pe_ratio       : '—',  ''),
    mc('52W HIGH',  fd.week52_high != null ? `$${fd.week52_high}` : '—', ''),
    mc('52W LOW',   fd.week52_low  != null ? `$${fd.week52_low}`  : '—', ''),
    mc('SENTIMENT', slb, sl),
    mc('RISK',      data.risk_flag ? 'HIGH' : 'STANDARD', rl),
  ].join('');
}
function mc(label, val, cls) {
  return `<div class="metric-cell"><div class="mlabel">${label}</div><div class="mval ${cls}">${esc(String(val))}</div></div>`;
}

// ── Result rendering ──────────────────────────────────────────────────────────
function renderResult(data) {
  resultCache[data.run_id] = data;

  el.resultEmpty.style.display = 'none';
  el.resultFull.style.display  = '';

  renderMetrics(data, el.metricsRow);
  showTicker(data.ticker, data.company_name, data.chat_response, data.risk_flag);

  populateTabs(data, {
    memo:  $('tab-memo'),
    risk:  $('tab-risk'),
    hedge: $('tab-hedge'),
    news:  $('tab-news'),
  });
}

function populateTabs(data, tabs) {
  // Brief
  tabs.memo.innerHTML = `<div class="memo-body">${mdToHtml(data.investment_memo || 'No memo generated.')}</div>`;

  // Risk
  const riskClass = data.risk_flag ? 'high' : 'low';
  const riskLabel = data.risk_flag ? '▲ HIGH RISK FLAGGED' : '✓ STANDARD RISK';
  tabs.risk.innerHTML = `
    <div class="risk-tag ${riskClass}">${riskLabel}</div>
    <div class="memo-body">${esc(data.analyst_rationale || 'No rationale available.')}</div>
  `;

  // Hedge
  tabs.hedge.innerHTML = `<div class="memo-body">${esc(data.hedging_strategies || 'No elevated risk — hedging not required.')}</div>`;

  // News
  const headlines = data.news_headlines || [];
  tabs.news.innerHTML = headlines.length
    ? headlines.map(h => `<div class="headline-item">${esc(h)}</div>`).join('')
    : '<p style="color:var(--text3);font-size:.72rem">No headlines retrieved.</p>';
}

// ── Tab switching (result card) ───────────────────────────────────────────────
document.querySelectorAll('.rtab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.rtab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.rtab-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    $(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

// ── Tab switching (modal) ─────────────────────────────────────────────────────
document.querySelectorAll('.mtab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.mtab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.mtab-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    $(tab.dataset.mtab).classList.add('active');
  });
});

// ── Stream ────────────────────────────────────────────────────────────────────
function openStream(runId) {
  closeStream();
  source = new EventSource(endpoint(`/api/v1/stream/${runId}`));
  setStreamState('warn', 'STREAMING');

  source.addEventListener('ticker', e => {
    const d = JSON.parse(e.data);
    showTicker(d.ticker, d.company_name, d.chat_response);
    appendLog('chat_node', 'done', `Identified: ${d.ticker} — ${d.company_name}`);
    setPipeState('chat_node', 'done');
    observedNodes.add('chat_node'); updateStats();
  });

  source.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    observedNodes.add(d.node); updateStats();
    setPipeState(d.node, 'running');
    appendLog(d.node, 'running', NODE_MSGS[d.node] || d.node);
  });

  source.addEventListener('complete', e => {
    const d = JSON.parse(e.data);
    // Mark all done
    NODES.forEach(n => setPipeState(n.id, 'done'));
    appendLog('reporter', 'done', 'Investment brief compiled');
    renderResult(d);
    showTicker(d.ticker, d.company_name, d.chat_response, d.risk_flag);
    completedRuns++; updateStats();
    stopDurationTimer();
    closeStream('done');
    refreshHistory();
  });

  source.addEventListener('error', async () => {
    try {
      if (currentRunId) {
        const s = await apiReq(`/api/v1/status/${currentRunId}`);
        if (s.status === 'completed') {
          const r = await apiReq(`/api/v1/result/${currentRunId}`);
          renderResult(r);
          NODES.forEach(n => setPipeState(n.id, 'done'));
          appendLog('fallback', 'done', 'Recovered via polling');
          completedRuns++; updateStats();
          stopDurationTimer();
          closeStream('done');
          refreshHistory();
          return;
        }
      }
    } catch (_) {}
    appendLog('stream', 'error', 'Stream disconnected');
    stopDurationTimer();
    closeStream('error');
    refreshHistory();
  });
}

function closeStream(outcome) {
  if (source) { source.close(); source = null; }
  setLoading(false);
  const states = { done:'ok', error:'bad' };
  const txts   = { done:'COMPLETE', error:'ERROR' };
  setStreamState(states[outcome] || 'neutral', txts[outcome] || 'IDLE');
}

// ── Form submit ───────────────────────────────────────────────────────────────
document.getElementById('analysisForm')?.addEventListener('submit', handleSubmit);
// fallback: button click if no form wrapping
document.getElementById('submitBtn')?.addEventListener('click', function(e) {
  // only fire if not inside a form submit
  if (!this.form) handleSubmit(e);
});

async function handleSubmit(e) {
  if (e) e.preventDefault();
  const query = el.query.value.trim();
  if (!query) return;

  // Reset
  observedNodes.clear(); updateStats();
  el.resultEmpty.style.display = '';
  el.resultFull.style.display  = 'none';
  el.tickerHero.style.display  = 'none';
  clearPipeline(); resetLog();
  setLoading(true);
  startDurationTimer();

  try {
    const start  = await apiReq('/api/v1/analyse', { method:'POST', body:JSON.stringify({query}) });
    currentRunId = start.run_id;
    updateStats();
    appendLog('api', 'running', `Run ${start.run_id.slice(0,8)}… accepted`);
    openStream(currentRunId);
  } catch (err) {
    appendLog('api', 'error', `Failed: ${err.message}`);
    stopDurationTimer();
    closeStream('error');
  }
}

el.stopBtn.addEventListener('click', () => {
  appendLog('user', 'error', 'Aborted by user');
  stopDurationTimer();
  closeStream('error');
});

// ── History feed ──────────────────────────────────────────────────────────────
async function refreshHistory() {
  try {
    const jobs = await apiReq('/api/v1/jobs');
    if (!Array.isArray(jobs) || !jobs.length) {
      el.historyFeed.innerHTML = '<div class="log-empty">No analyses yet this session.</div>';
      return;
    }
    completedRuns = Math.max(completedRuns, jobs.filter(j => j.status==='completed').length);
    updateStats();

    el.historyFeed.innerHTML = '';
    jobs.slice(0, 20).forEach(job => {
      const card = document.createElement('div');
      card.className = 'hist-card';

      // Try to get cached result data for richer display
      const cached = resultCache[job.run_id];
      const fd      = cached?.financial_data || {};
      const s       = cached?.sentiment_score;
      const sentCls = s > 0.1 ? 'bull' : s < -0.1 ? 'bear' : 'neut';
      const sentLbl = s > 0.1 ? '↑ BULLISH' : s < -0.1 ? '↓ BEARISH' : '→ NEUTRAL';

      card.innerHTML = `
        <div class="hist-ticker">${esc(job.ticker || '??')}</div>
        <div class="hist-company">${esc(cached?.company_name || job.ticker || '—')}</div>
        <div class="hist-query">${esc(job.user_query || 'Untitled')}</div>
        <div class="hist-meta">
          <span class="hist-status ${job.status}">${(job.status||'?').toUpperCase()}</span>
          ${fd.price ? `<span class="hist-price">$${fd.price}</span>` : ''}
          ${s !== undefined ? `<span class="hist-sentiment ${sentCls}">${sentLbl}</span>` : ''}
        </div>
      `;

      card.addEventListener('click', () => openModal(job.run_id));
      el.historyFeed.appendChild(card);
    });
  } catch (err) {
    el.historyFeed.innerHTML = `<div class="log-empty">Error: ${esc(err.message)}</div>`;
  }
}

// ── History modal ─────────────────────────────────────────────────────────────
async function openModal(runId) {
  let data = resultCache[runId];

  if (!data) {
    try {
      data = await apiReq(`/api/v1/result/${runId}`);
      resultCache[runId] = data;
    } catch {
      return; // job not done yet
    }
  }

  el.modalTicker.textContent  = data.ticker  || '—';
  el.modalCompany.textContent = data.company_name || '';
  renderMetrics(data, el.modalMetrics);

  populateTabs(data, {
    memo:  $('mmemo'),
    risk:  $('mrisk'),
    hedge: $('mhedge'),
    news:  $('mnews'),
  });

  // Reset modal tabs to first
  document.querySelectorAll('.mtab').forEach((t,i) => t.classList.toggle('active', i===0));
  document.querySelectorAll('.mtab-panel').forEach((p,i) => p.classList.toggle('active', i===0));

  el.modalOverlay.style.display = 'flex';
  document.body.style.overflow  = 'hidden';
}

el.modalClose.addEventListener('click', closeModal);
el.modalOverlay.addEventListener('click', e => { if (e.target===el.modalOverlay) closeModal(); });
document.addEventListener('keydown', e => { if (e.key==='Escape') closeModal(); });

function closeModal() {
  el.modalOverlay.style.display = 'none';
  document.body.style.overflow  = '';
}

el.refreshHistBtn.addEventListener('click', refreshHistory);

// ── Markdown → HTML (light parser) ───────────────────────────────────────────
function mdToHtml(md) {
  return md
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    // tables
    .replace(/^\|(.+)\|$/gm, '<tr>$1</tr>')
    .replace(/<tr>(.+)<\/tr>/g, m =>
      '<tr>' + m.slice(4,-5).split('|').filter(Boolean).map(c => `<td>${c.trim()}</td>`).join('') + '</tr>')
    .replace(/(<tr>.*<\/tr>)/s, '<table>$1</table>')
    // headers
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3 style="color:var(--cyan);font-family:var(--mono);font-size:.8rem;letter-spacing:.1em;margin:.8rem 0 .3rem">$3</h3>')
    // bold / italic
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    // lists
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^  • (.+)$/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // paragraphs
    .split(/\n{2,}/).map(block => {
      if (block.startsWith('<h') || block.startsWith('<table') || block.startsWith('<li')) return block;
      if (block.includes('<li>')) return `<ul>${block}</ul>`;
      return `<p>${block.replace(/\n/g,' ')}</p>`;
    }).join('\n');
}

// ── Escape HTML ───────────────────────────────────────────────────────────────
function esc(t) {
  return String(t||'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

// ── SVG icons ─────────────────────────────────────────────────────────────────
function iconChat()   { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`; }
function iconChart()  { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`; }
function iconSearch() { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`; }
function iconBrain()  { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-1.14z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-1.14z"/></svg>`; }
function iconShield() { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`; }
function iconDoc()    { return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`; }

// ── Init ──────────────────────────────────────────────────────────────────────
buildPipeline();
checkHealth();
refreshHistory();
updateStats();