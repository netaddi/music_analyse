const state = {
  currentJobId: null,
  pollHandle: null,
};

const elements = {
  uploadForm: document.querySelector('#upload-form'),
  fileInput: document.querySelector('#file-input'),
  healthBadge: document.querySelector('#health-badge'),
  healthCopy: document.querySelector('#health-copy'),
  progressSteps: document.querySelectorAll('#progress-steps li'),
  jobStatus: document.querySelector('#job-status'),
  errorMessage: document.querySelector('#error-message'),
  overallScore: document.querySelector('#overall-score'),
  riskPill: document.querySelector('#risk-pill'),
  summaryHeadline: document.querySelector('#summary-headline'),
  topIssue: document.querySelector('#top-issue'),
  platformTrim: document.querySelector('#platform-trim'),
  summaryConfidence: document.querySelector('#summary-confidence'),
  techInfo: document.querySelector('#tech-info'),
  categoryCards: document.querySelector('#category-cards'),
  chartGrid: document.querySelector('#chart-grid'),
  recommendationList: document.querySelector('#recommendation-list'),
  recommendationTemplate: document.querySelector('#recommendation-template'),
};

const severityClass = (severity) => `severity-${severity}`;

async function fetchHealth() {
  try {
    const response = await fetch('/healthz');
    const payload = await response.json();
    elements.healthBadge.textContent = payload.status === 'ok' ? 'Healthy' : 'Degraded';
    elements.healthCopy.textContent = 'Backend API is reachable.';
  } catch (error) {
    elements.healthBadge.textContent = 'Offline';
    elements.healthCopy.textContent = 'Unable to reach the backend API.';
  }
}

function setProgress(stage) {
  const stageOrder = ['Queued', 'Reading metadata', 'Decoding audio', 'Computing metrics', 'Generating report', 'Completed'];
  const currentIndex = stageOrder.indexOf(stage);

  elements.progressSteps.forEach((item, index) => {
    item.classList.remove('active', 'complete');
    const itemStage = item.dataset.stage;
    const itemIndex = stageOrder.indexOf(itemStage);
    if (itemIndex === -1 || currentIndex === -1) {
      return;
    }
    if (itemIndex < currentIndex) {
      item.classList.add('complete');
    } else if (itemIndex === currentIndex) {
      item.classList.add('active');
    }
  });
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorMessage.classList.remove('hidden');
}

function clearError() {
  elements.errorMessage.textContent = '';
  elements.errorMessage.classList.add('hidden');
}

function buildInfoCard(label, value) {
  const card = document.createElement('article');
  card.className = 'info-card';
  card.innerHTML = `<p class="muted-copy">${label}</p><strong>${value}</strong>`;
  return card;
}

function renderTechInfo(technicalInfo) {
  const entries = [
    ['Format', technicalInfo.format_name],
    ['Codec', technicalInfo.codec_name],
    ['Sample rate', `${technicalInfo.sample_rate} Hz`],
    ['Channels', `${technicalInfo.channels}`],
    ['Duration', `${technicalInfo.duration_seconds.toFixed(2)} s`],
    ['Bitrate', technicalInfo.bit_rate_kbps ? `${technicalInfo.bit_rate_kbps.toFixed(0)} kbps` : 'n/a'],
    ['Bits per sample', technicalInfo.bits_per_sample ?? 'n/a'],
    ['File size', `${(technicalInfo.file_size_bytes / (1024 * 1024)).toFixed(2)} MB`],
  ];

  elements.techInfo.replaceChildren(...entries.map(([label, value]) => buildInfoCard(label, value)));
}

function renderCategories(categories) {
  const cards = categories.map((category) => {
    const card = document.createElement('article');
    card.className = 'category-card';
    card.innerHTML = `
      <header>
        <div>
          <p class="eyebrow">${category.name}</p>
          <strong>${category.summary}</strong>
        </div>
        <span class="score-chip ${severityClass(category.severity)}">${category.score.toFixed(0)}</span>
      </header>
      <p class="muted-copy">${category.details}</p>
      <p class="muted-copy">Confidence: ${(category.confidence * 100).toFixed(0)}%</p>
    `;
    return card;
  });

  elements.categoryCards.replaceChildren(...cards);
}

function makeSvgSurface(viewBox, body) {
  return `
    <svg viewBox="${viewBox}" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="lineGradient" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#4cd2ff" />
          <stop offset="100%" stop-color="#ff7d5c" />
        </linearGradient>
      </defs>
      ${body}
    </svg>
  `;
}

function lineChartMarkup(chart) {
  const width = 100;
  const height = 100;
  const values = chart.series[0]?.values ?? [];
  if (!values.length) {
    return makeSvgSurface(`0 0 ${width} ${height}`, '');
  }

  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const range = maxValue - minValue || 1;

  const path = values
    .map((value, index) => {
      const x = values.length === 1 ? 0 : (index / (values.length - 1)) * width;
      const y = height - ((value - minValue) / range) * (height - 6) - 3;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');

  return makeSvgSurface(
    `0 0 ${width} ${height}`,
    `<path d="${path}" fill="none" stroke="url(#lineGradient)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />`
  );
}

function barChartMarkup(chart) {
  const width = 100;
  const height = 100;
  const values = chart.series[0]?.values ?? [];
  if (!values.length) {
    return makeSvgSurface(`0 0 ${width} ${height}`, '');
  }
  const maxValue = Math.max(...values) || 1;
  const barWidth = width / values.length;
  const bars = values
    .map((value, index) => {
      const x = index * barWidth + 4;
      const barHeight = (value / maxValue) * 82;
      const y = height - barHeight - 6;
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(barWidth - 8, 6).toFixed(2)}" height="${barHeight.toFixed(2)}" rx="4" fill="rgba(255, 125, 92, 0.86)" />`;
    })
    .join('');
  return makeSvgSurface(`0 0 ${width} ${height}`, bars);
}

function renderCharts(charts) {
  const cards = Object.values(charts).map((chart) => {
    const card = document.createElement('article');
    card.className = 'chart-card';
    const graphic = chart.kind === 'bar' ? barChartMarkup(chart) : lineChartMarkup(chart);
    const labels = chart.labels?.length ? `<p class="muted-copy">${chart.labels.join(' | ')}</p>` : '';
    card.innerHTML = `
      <header>
        <div>
          <p class="eyebrow">${chart.kind}</p>
          <strong>${chart.title}</strong>
        </div>
      </header>
      <div class="chart-surface">${graphic}</div>
      <p class="muted-copy">${chart.y_label}</p>
      ${labels}
    `;
    return card;
  });

  elements.chartGrid.replaceChildren(...cards);
}

function renderRecommendations(recommendations) {
  const items = recommendations.map((recommendation) => {
    const fragment = elements.recommendationTemplate.content.cloneNode(true);
    const details = fragment.querySelector('details');
    const title = fragment.querySelector('.accordion-title');
    const summary = fragment.querySelector('.accordion-summary');
    const tag = fragment.querySelector('.severity-tag');
    const evidenceList = fragment.querySelector('.evidence-list');
    const actionList = fragment.querySelector('.action-list');

    title.textContent = recommendation.title;
    summary.textContent = recommendation.summary;
    tag.textContent = recommendation.severity;
    tag.classList.add(severityClass(recommendation.severity));

    recommendation.evidence.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      evidenceList.appendChild(li);
    });

    recommendation.actions.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      actionList.appendChild(li);
    });

    return details;
  });

  elements.recommendationList.replaceChildren(...items);
}

function renderReport(report) {
  elements.overallScore.textContent = report.summary.overall_score.toFixed(0);
  elements.riskPill.textContent = report.summary.risk_level;
  elements.summaryHeadline.textContent = report.summary.headline;
  elements.topIssue.textContent = report.summary.top_issue;
  elements.platformTrim.textContent = `${report.summary.estimated_platform_attenuation_db.toFixed(1)} dB`;
  elements.summaryConfidence.textContent = `${(report.summary.confidence * 100).toFixed(0)}%`;
  renderTechInfo(report.technical_info);
  renderCategories(report.categories);
  renderCharts(report.charts);
  renderRecommendations(report.recommendations);
}

async function fetchReport(reportId) {
  const response = await fetch(`/api/reports/${reportId}`);
  if (!response.ok) {
    throw new Error('Failed to load generated report.');
  }
  return response.json();
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error('Failed to poll analysis job.');
  }
  const job = await response.json();
  elements.jobStatus.textContent = `${job.status}: ${job.stage}`;
  setProgress(job.stage);

  if (job.status === 'failed') {
    if (state.pollHandle) {
      clearInterval(state.pollHandle);
    }
    state.pollHandle = null;
    showError(job.error || 'Analysis failed.');
    return;
  }

  if (job.status === 'completed' && job.report_id) {
    if (state.pollHandle) {
      clearInterval(state.pollHandle);
    }
    state.pollHandle = null;
    const report = await fetchReport(job.report_id);
    renderReport(report);
  }
}

async function submitAnalysis(event) {
  event.preventDefault();
  clearError();

  const file = elements.fileInput.files?.[0];
  if (!file) {
    showError('Choose an audio file first.');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  elements.jobStatus.textContent = 'Submitting analysis job...';
  setProgress('Queued');

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.detail || 'Failed to submit analysis job.');
    }

    const payload = await response.json();
    state.currentJobId = payload.job_id;
    elements.jobStatus.textContent = `${payload.status}: ${payload.stage}`;

    if (state.pollHandle) {
      clearInterval(state.pollHandle);
    }
    state.pollHandle = setInterval(() => {
      pollJob(payload.job_id).catch((error) => {
        clearInterval(state.pollHandle);
        state.pollHandle = null;
        showError(error.message);
      });
    }, 1000);

    await pollJob(payload.job_id);
  } catch (error) {
    showError(error.message);
  }
}

elements.uploadForm.addEventListener('submit', submitAnalysis);
fetchHealth();
