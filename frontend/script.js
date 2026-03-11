const els = {
  form: document.getElementById('analysisForm'),
  query: document.getElementById('query'),
  submitBtn: document.getElementById('submitBtn'),
  stopBtn: document.getElementById('stopBtn'),
  apiBase: document.getElementById('apiBase'),
  health: document.getElementById('backendHealth'),
  streamHealth: document.getElementById('streamHealth'),
  progressList: document.getElementById('progressList'),
  streamState: document.getElementById('streamState'),
  result: document.getElementById('result'),
  jobs: document.getElementById('jobs'),
  refreshJobsBtn: document.getElementById('refreshJobsBtn'),
  nodeCount: document.getElementById('nodeCount'),
  lastRunId: document.getElementById('lastRunId'),
  completedCount: document.getElementById('completedCount'),
};

let currentRunId = null;
let source = null;
let completedRuns = 0;
const observedNodes = new Set();

const storageKey = 'finagent.apiBase';
els.apiBase.value = localStorage.getItem(storageKey) || '';
els.apiBase.addEventListener('change', () => {
  localStorage.setItem(storageKey, els.apiBase.value.trim());
  checkHealth();
});

function escapeHtml(text) {
  return String(text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatValue(value) {
  return value === null || value === undefined || value === '' ? '—' : escapeHtml(value);
}

function apiBase() {
  return (els.apiBase.value || '').trim().replace(/\/$/, '');
}

function endpoint(path) {
  const base = apiBase();
  return base ? `${base}${path}` : path;
}

function setLoading(isLoading) {
  els.submitBtn.disabled = isLoading;
  els.stopBtn.disabled = !isLoading;
}

function setStreamHealth(label, tone = 'neutral') {
  els.streamHealth.textContent = label;
  els.streamHealth.className = `status-chip ${tone}`;
}

function updateStats() {
  els.nodeCount.textContent = String(observedNodes.size);
  els.lastRunId.textContent = currentRunId || '—';
  els.completedCount.textContent = String(completedRuns);
}

async function apiRequest(path, options = {}) {
  const res = await fetch(endpoint(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `Request failed: ${res.status}`);
  }

  if (res.status === 204) {
    return null;
  }

  return res.json();
}

function renderProgress(node, status, message = '') {
  observedNodes.add(node);
  updateStats();

  const li = document.createElement('li');
  const badgeClass = status === 'completed' ? 'ok' : status === 'error' ? 'bad' : 'warn';
  const safeMessage = message ? `<p>${escapeHtml(message)}</p>` : '';
  li.innerHTML = `
    <div>
      <strong>${escapeHtml(node)}</strong>
      ${safeMessage}
    </div>
    <span class="badge ${badgeClass}">${escapeHtml(status)}</span>
  `;
  els.progressList.prepend(li);
}

function renderResult(data) {
  const fd = data.financial_data || {};
  els.result.innerHTML = `
    <article class="result-content">
      <div class="result-hero">
        <h3>${formatValue(data.company_name || data.ticker || 'Unknown')}</h3>
        <span class="badge neutral">${formatValue(data.ticker)}</span>
      </div>

      <div class="metric-grid">
        <div class="metric"><p>Price</p><strong>${formatValue(fd.price)}</strong></div>
        <div class="metric"><p>P/E</p><strong>${formatValue(fd.pe_ratio)}</strong></div>
        <div class="metric"><p>52W High</p><strong>${formatValue(fd.week52_high)}</strong></div>
        <div class="metric"><p>52W Low</p><strong>${formatValue(fd.week52_low)}</strong></div>
      </div>

      <section>
        <h4>Analyst Rationale</h4>
        <pre>${formatValue(data.analyst_rationale || 'N/A')}</pre>
      </section>

      <section>
        <h4>Investment Memo</h4>
        <pre>${formatValue(data.investment_memo || 'N/A')}</pre>
      </section>

      <section>
        <h4>Hedging Strategies</h4>
        <pre>${formatValue(data.hedging_strategies || 'N/A')}</pre>
      </section>
    </article>
  `;
}

function closeStream(streamStateText = 'No active stream.') {
  if (source) {
    source.close();
    source = null;
  }

  setLoading(false);
  els.streamState.textContent = streamStateText;
  if (streamStateText.toLowerCase().includes('error')) {
    setStreamHealth('Stream error', 'bad');
  } else if (streamStateText.toLowerCase().includes('completed')) {
    setStreamHealth('Stream completed', 'ok');
  } else {
    setStreamHealth('Stream idle', 'neutral');
  }
}

function openStream(runId) {
  closeStream();
  const url = endpoint(`/api/v1/stream/${runId}`);
  source = new EventSource(url);
  els.streamState.textContent = `Streaming run ${runId}…`;
  setStreamHealth('Streaming', 'warn');

  source.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);
    renderProgress(data.node, data.status, data.message || '');
  });

  source.addEventListener('ticker', (event) => {
    const data = JSON.parse(event.data);
    renderProgress(`ticker:${data.ticker}`, 'running', 'Detected target symbol');
  });

  source.addEventListener('complete', (event) => {
    const data = JSON.parse(event.data);
    renderProgress('reporter', 'completed', 'Final investment memo generated');
    renderResult(data);
    completedRuns += 1;
    updateStats();
    closeStream('Completed.');
    refreshJobs();
  });

  source.addEventListener('error', async (event) => {
    console.error('SSE error', event);
    try {
      if (currentRunId) {
        const status = await apiRequest(`/api/v1/status/${currentRunId}`);
        if (status.status === 'completed') {
          const result = await apiRequest(`/api/v1/result/${currentRunId}`);
          renderResult(result);
          renderProgress('fallback-fetch', 'completed', 'Recovered final result after stream disconnect');
          completedRuns += 1;
          updateStats();
          closeStream('Completed with fallback fetch.');
        } else {
          renderProgress('stream', 'running', 'Disconnected temporarily; retry by refreshing status');
          closeStream('Stream interrupted before completion.');
        }
      }
    } catch (err) {
      closeStream(`Stream error: ${err.message}`);
    } finally {
      refreshJobs();
    }
  });
}

async function refreshJobs() {
  try {
    const jobs = await apiRequest('/api/v1/jobs');
    if (!Array.isArray(jobs) || jobs.length === 0) {
      els.jobs.innerHTML = '<div class="muted">No jobs yet.</div>';
      return;
    }

    const completed = jobs.filter((job) => job.status === 'completed').length;
    completedRuns = Math.max(completedRuns, completed);
    updateStats();

    els.jobs.innerHTML = jobs
      .slice(0, 12)
      .map((job) => {
        const cls = job.status === 'completed' ? 'ok' : job.status === 'error' ? 'bad' : 'warn';
        return `
          <article class="job-row">
            <div>
              <strong>${formatValue(job.user_query || 'Untitled query')}</strong>
              <p class="muted">Run ID: ${formatValue(job.run_id || '-')}</p>
            </div>
            <div class="job-meta">
              <span>${formatValue(job.ticker || 'UNKNOWN')}</span>
              <span class="badge ${cls}">${formatValue(job.status || 'unknown')}</span>
            </div>
          </article>
        `;
      })
      .join('');
  } catch (err) {
    els.jobs.innerHTML = `<div class="muted">Unable to load jobs: ${escapeHtml(err.message)}</div>`;
  }
}

async function checkHealth() {
  try {
    const data = await apiRequest('/health');
    const isHealthy = data.status === 'healthy';
    els.health.textContent = isHealthy ? 'Backend connected' : 'Backend check unknown';
    els.health.className = `status-chip ${isHealthy ? 'ok' : 'warn'}`;
  } catch {
    els.health.textContent = 'Backend unreachable';
    els.health.className = 'status-chip bad';
  }
}

els.form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const query = els.query.value.trim();
  if (!query) {
    return;
  }

  els.progressList.innerHTML = '';
  observedNodes.clear();
  updateStats();
  els.result.innerHTML = '<div class="result-placeholder">Running analysis pipeline…</div>';

  setLoading(true);
  try {
    const start = await apiRequest('/api/v1/analyse', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
    currentRunId = start.run_id;
    updateStats();
    renderProgress('start', 'running', 'Run accepted by backend');
    openStream(currentRunId);
  } catch (err) {
    closeStream(`Failed to start analysis: ${err.message}`);
  }
});

els.stopBtn.addEventListener('click', () => {
  closeStream('Stream stopped by user.');
});

els.refreshJobsBtn.addEventListener('click', refreshJobs);

checkHealth();
refreshJobs();
updateStats();
