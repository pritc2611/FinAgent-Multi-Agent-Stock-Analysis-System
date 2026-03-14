/* FinAgent Console — script.js
   ─────────────────────────────────────────────────────────────────────────
   Architecture (HuggingFace Spaces):
     FastAPI on port 7860 serves BOTH the API (/api/v1/*) AND the frontend
     static files (/, /style.css, /script.js).
     The browser loads the page from https://user-space.hf.space and all
     fetch() calls go to the SAME origin — no CORS, no port mismatch.

   Local dev override:
     If you're running frontend separately, open Connection Settings and
     paste your backend URL. It's saved to localStorage.
   ─────────────────────────────────────────────────────────────────────────
*/

const $ = id => document.getElementById(id);

const els = {
  form:            $('analysisForm'),
  query:           $('query'),
  submitBtn:       $('submitBtn'),
  stopBtn:         $('stopBtn'),
  apiBase:         $('apiBase'),
  health:          $('backendHealth'),
  streamHealth:    $('streamHealth'),
  progressList:    $('progressList'),
  streamState:     $('streamState'),
  result:          $('result'),
  jobs:            $('jobs'),
  refreshJobsBtn:  $('refreshJobsBtn'),
  nodeCount:       $('nodeCount'),
  lastRunId:       $('lastRunId'),
  completedCount:  $('completedCount'),
};

let currentRunId  = null;
let source        = null;
let completedRuns = 0;
const observedNodes = new Set();

const STORAGE_KEY = 'finagent.apiBase';

// Restore any saved override
els.apiBase.value = localStorage.getItem(STORAGE_KEY) || '';
els.apiBase.addEventListener('change', () => {
  localStorage.setItem(STORAGE_KEY, els.apiBase.value.trim());
  checkHealth();
});

// ── URL resolution ────────────────────────────────────────────────────────────
// Default is EMPTY STRING → all fetch() calls use relative URLs → same origin.
// This works perfectly on HuggingFace Spaces where FastAPI serves the frontend.
// Override only needed when running frontend and backend on different hosts.
function apiBase() {
  const override = (els.apiBase.value || localStorage.getItem(STORAGE_KEY) || '').trim().replace(/\/$/, '');
  return override; // empty string = same-origin (correct for HF Spaces)
}

function endpoint(path) {
  const base = apiBase();
  return base ? `${base}${path}` : path; // relative URL when no override
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escapeHtml(text) {
  return String(text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function fv(v) {
  return (v === null || v === undefined || v === '') ? '—' : escapeHtml(String(v));
}

function setLoading(on) {
  els.submitBtn.disabled = on;
  els.stopBtn.disabled   = !on;
  els.submitBtn.textContent = on ? 'Running…' : 'Start Analysis';
}

function setStreamHealth(label, tone = 'neutral') {
  els.streamHealth.textContent = label;
  els.streamHealth.className   = `status-chip ${tone}`;
}

function updateStats() {
  els.nodeCount.textContent      = String(observedNodes.size);
  els.lastRunId.textContent      = currentRunId || '—';
  els.completedCount.textContent = String(completedRuns);
}

async function apiRequest(path, options = {}) {
  const res = await fetch(endpoint(path), {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

// ── Progress timeline ─────────────────────────────────────────────────────────
function renderProgress(node, status, message = '') {
  observedNodes.add(node);
  updateStats();
  const li = document.createElement('li');
  const badgeClass = status === 'completed' ? 'ok' : status === 'error' ? 'bad' : 'warn';
  li.innerHTML = `
    <div>
      <strong>${escapeHtml(node)}</strong>
      ${message ? `<p>${escapeHtml(message)}</p>` : ''}
    </div>
    <span class="badge ${badgeClass}">${escapeHtml(status)}</span>
  `;
  els.progressList.prepend(li);
}

// ── Result rendering ──────────────────────────────────────────────────────────
function renderResult(data) {
  const fd = data.financial_data || {};
  els.result.innerHTML = `
    <article class="result-content">
      <div class="result-hero">
        <h3>${fv(data.company_name || data.ticker || 'Unknown')}</h3>
        <span class="badge neutral">${fv(data.ticker)}</span>
      </div>
      <div class="metric-grid">
        <div class="metric"><p>Price</p><strong>${fv(fd.price)}</strong></div>
        <div class="metric"><p>P/E</p><strong>${fv(fd.pe_ratio)}</strong></div>
        <div class="metric"><p>52W High</p><strong>${fv(fd.week52_high)}</strong></div>
        <div class="metric"><p>52W Low</p><strong>${fv(fd.week52_low)}</strong></div>
      </div>
      <section>
        <h4>Analyst Rationale</h4>
        <pre>${fv(data.analyst_rationale || 'N/A')}</pre>
      </section>
      <section>
        <h4>Investment Memo</h4>
        <pre>${fv(data.investment_memo || 'N/A')}</pre>
      </section>
      <section>
        <h4>Hedging Strategies</h4>
        <pre>${fv(data.hedging_strategies || 'N/A – no elevated risk.')}</pre>
      </section>
    </article>
  `;
}

// ── SSE stream ────────────────────────────────────────────────────────────────
function closeStream(msg = 'No active stream.') {
  if (source) { source.close(); source = null; }
  setLoading(false);
  els.streamState.textContent = msg;
  const tone = msg.toLowerCase().includes('error') ? 'bad'
             : msg.toLowerCase().includes('complet') ? 'ok'
             : 'neutral';
  setStreamHealth(
    tone === 'bad' ? 'Stream error' : tone === 'ok' ? 'Stream complete' : 'Stream idle',
    tone
  );
}

function openStream(runId) {
  closeStream();
  source = new EventSource(endpoint(`/api/v1/stream/${runId}`));
  els.streamState.textContent = `Streaming run ${runId}…`;
  setStreamHealth('Streaming…', 'warn');

  source.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    renderProgress(d.node, d.status, d.message || '');
  });

  source.addEventListener('ticker', e => {
    const d = JSON.parse(e.data);
    renderProgress(`ticker: ${d.ticker}`, 'running', d.company_name || '');
  });

  source.addEventListener('complete', e => {
    const d = JSON.parse(e.data);
    renderProgress('reporter', 'completed', 'Investment brief generated');
    renderResult(d);
    completedRuns++;
    updateStats();
    closeStream('Completed.');
    refreshJobs();
  });

  source.addEventListener('error', async () => {
    // SSE error — try polling fallback before giving up
    try {
      if (currentRunId) {
        const status = await apiRequest(`/api/v1/status/${currentRunId}`);
        if (status.status === 'completed') {
          const result = await apiRequest(`/api/v1/result/${currentRunId}`);
          renderResult(result);
          renderProgress('fallback', 'completed', 'Recovered via polling');
          completedRuns++;
          updateStats();
          closeStream('Completed (fallback).');
          return;
        }
      }
    } catch (_) { /* ignore */ }
    closeStream('Stream interrupted.');
    refreshJobs();
  });
}

// ── Form submit ───────────────────────────────────────────────────────────────
els.form.addEventListener('submit', async e => {
  e.preventDefault();
  const query = els.query.value.trim();
  if (!query) return;

  els.progressList.innerHTML = '';
  observedNodes.clear();
  updateStats();
  els.result.innerHTML = '<div class="result-placeholder">Running analysis pipeline…</div>';
  setLoading(true);

  try {
    const start    = await apiRequest('/api/v1/analyse', {
      method: 'POST',
      body:   JSON.stringify({ query }),
    });
    currentRunId   = start.run_id;
    updateStats();
    renderProgress('start', 'running', 'Run accepted by backend');
    openStream(currentRunId);
  } catch (err) {
    closeStream(`Failed to start: ${err.message}`);
  }
});

els.stopBtn.addEventListener('click', () => closeStream('Stopped by user.'));
els.refreshJobsBtn.addEventListener('click', refreshJobs);

// ── Jobs history ──────────────────────────────────────────────────────────────
async function refreshJobs() {
  try {
    const jobs = await apiRequest('/api/v1/jobs');
    if (!Array.isArray(jobs) || jobs.length === 0) {
      els.jobs.innerHTML = '<div class="muted">No jobs yet.</div>';
      return;
    }
    completedRuns = Math.max(completedRuns, jobs.filter(j => j.status === 'completed').length);
    updateStats();
    els.jobs.innerHTML = jobs.slice(0, 12).map(job => {
      const cls = job.status === 'completed' ? 'ok' : job.status === 'error' ? 'bad' : 'warn';
      return `
        <article class="job-row">
          <div>
            <strong>${fv(job.user_query || 'Untitled')}</strong>
            <p class="muted">Run ID: ${fv(job.run_id)}</p>
          </div>
          <div class="job-meta">
            <span>${fv(job.ticker || '??')}</span>
            <span class="badge ${cls}">${fv(job.status)}</span>
          </div>
        </article>`;
    }).join('');
  } catch (err) {
    els.jobs.innerHTML = `<div class="muted">Could not load jobs: ${escapeHtml(err.message)}</div>`;
  }
}

// ── Health check ──────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const data = await apiRequest('/health');
    const ok   = data.status === 'healthy';
    els.health.textContent = ok ? 'Backend connected' : 'Backend uncertain';
    els.health.className   = `status-chip ${ok ? 'ok' : 'warn'}`;
  } catch {
    els.health.textContent = 'Backend unreachable';
    els.health.className   = 'status-chip bad';
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
checkHealth();
refreshJobs();
updateStats();