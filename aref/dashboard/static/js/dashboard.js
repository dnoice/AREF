/*
* ============================================================================
* ✒ Metadata
*     - Title: AREF Dashboard Client (AREF Edition - v2.0)
*     - File Name: dashboard.js
*     - Relative Path: aref/dashboard/static/js/dashboard.js
*     - Artifact Type: script
*     - Version: 2.0.0
*     - Date: 2026-03-13
*     - Update: Thursday, March 13, 2026
*     - Author: Dennis 'dnoice' Smaltz
*     - A.I. Acknowledgement: Anthropic - Claude Opus 4
*     - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
*
* ✒ Description:
*     Client-side JavaScript application powering the AREF Dashboard. Handles
*     real-time data polling, diffed DOM updates with CSS transition support,
*     SVG radar chart rendering, CRS gauge animation, pillar-specific detail
*     views, chaos experiment controls, and metrics visualization — all without
*     external framework dependencies (vanilla JS).
*
* ✒ Key Features:
*     - Feature 1: 5-second polling loop fetching status, services, alerts, and
*                   timeline data from the AREF REST API
*     - Feature 2: Smooth number interpolation with easeInOutQuad easing for
*                   CRS score, maturity levels, and KPI card values
*     - Feature 3: SVG-based radar chart rendering maturity scores across all
*                   five pillars with animated polygon transitions
*     - Feature 4: CRS gauge with dynamic arc coloring (red → amber → green)
*                   and real-time score display
*     - Feature 5: Pillar card grid with severity-aware color coding, maturity
*                   level names, and score-driven progress indicators
*     - Feature 6: Detection detail panel — alert stats, threshold rule status,
*                   anomaly stream stats, synthetic probe results, SLI/SLO
*                   compliance, and configuration display
*     - Feature 7: Absorption detail panel — circuit breaker state matrix,
*                   rate limiter utilization, bulkhead concurrency, blast radius
*                   dependency map, and degradation tier management
*     - Feature 8: Adaptation detail panel — feature flag toggle grid, traffic
*                   route weight bars, auto-scaler instance counts, decision
*                   tree strategy reference, and adaptation history log
*     - Feature 9: Recovery detail panel — tier definition cards (T0–T4),
*                   runbook catalog with expandable step details, execution
*                   history, and drill compliance tracking
*     - Feature 10: Evolution detail panel — six-step review process tracker,
*                    action item board with overdue highlighting, pattern
*                    matching results, knowledge base entries, and metrics
*     - Feature 11: Metrics page — MTTD/MTTR/Availability/Incidents KPI cards,
*                    error budget gauges per SLO tier, CRS across all four risk
*                    profiles, weight distribution chart, and pillar score bars
*     - Feature 12: Chaos Lab controls — experiment selector with start/stop
*                    buttons and active injection status display
*     - Feature 13: Event timeline with severity-colored entries and timestamps
*     - Feature 14: Section-based navigation with active state management
*     - Feature 15: Diffed DOM updates — innerHTML only on first render,
*                    subsequent updates patch individual elements to preserve
*                    CSS transitions and avoid flicker
*
* ✒ Usage Instructions:
*     Loaded automatically by index.html via:
*         <script src="/static/js/dashboard.js"></script>
*
*     Self-initializing IIFE — no manual setup required. Begins polling
*     immediately on page load. Navigation exposed globally:
*         navigate('detection')   — switch to Detection pillar view
*         refreshData()           — force immediate data refresh
*         refreshMetrics()        — force metrics page refresh
*         startChaos(experiment)  — trigger a chaos experiment
*         stopChaos()             — stop all active chaos injections
*
* ✒ Other Important Information:
*     - Dependencies: None (vanilla JavaScript ES2020+)
*     - Compatible platforms: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
*     - Performance notes: requestAnimationFrame-driven animations; DOM diffing
*       minimizes reflows; polling is non-blocking via async/await
*     - Security considerations: No user input sanitization on API responses —
*       assumes trusted backend; no XSS vectors in current implementation
*     - Known limitations: No WebSocket support (polling only); radar chart
*       uses fixed 5-pillar layout; no local storage persistence of state;
*       chaos controls require backend connectivity
* ----------------------------------------------------------------------------
 */

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Configuration
  // ---------------------------------------------------------------------------
  const API_BASE = window.location.origin;
  const POLL_INTERVAL = 5000;
  const PILLAR_COLORS = {
    detection: '#3b82f6',
    absorption: '#8b5cf6',
    adaptation: '#f59e0b',
    recovery: '#10b981',
    evolution: '#ec4899',
  };
  const PILLAR_KEYS = ['detection', 'absorption', 'adaptation', 'recovery', 'evolution'];
  const PILLAR_LABELS = ['Detection', 'Absorption', 'Adaptation', 'Recovery', 'Evolution'];
  const LEVEL_NAMES = ['', 'Reactive', 'Managed', 'Defined', 'Measured', 'Optimizing'];

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  let state = {
    crs: 0,
    pillars: { detection: 1, absorption: 1, adaptation: 1, recovery: 1, evolution: 1 },
    services: {},
    alerts: [],
    incidents: [],
    timeline: [],
    maturity: {},
    chaosActive: false,
  };

  // Track whether components have been initialized (first render = innerHTML, subsequent = diffed)
  let initialized = {
    gauge: false,
    radar: false,
    pillarCards: false,
    services: false,
    alerts: false,
    timeline: false,
  };

  // ---------------------------------------------------------------------------
  // Utility: smooth number interpolation
  // ---------------------------------------------------------------------------
  function animateValue(el, from, to, duration = 600, decimals = 2) {
    if (Math.abs(from - to) < 0.001) return;
    const start = performance.now();
    function tick(now) {
      const t = Math.min((now - start) / duration, 1);
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; // easeInOutQuad
      el.textContent = (from + (to - from) * eased).toFixed(decimals);
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ---------------------------------------------------------------------------
  // Utility
  // ---------------------------------------------------------------------------
  function setText(selector, text) {
    const el = document.querySelector(selector);
    if (el) el.textContent = String(text);
  }

  // API Client
  // ---------------------------------------------------------------------------
  async function fetchJSON(endpoint) {
    try {
      const resp = await fetch(`${API_BASE}${endpoint}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (err) {
      console.error(`Fetch error: ${endpoint}`, err);
      return null;
    }
  }

  async function postJSON(endpoint, body = {}) {
    try {
      const resp = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return await resp.json();
    } catch (err) {
      console.error(`Post error: ${endpoint}`, err);
      return null;
    }
  }

  // ---------------------------------------------------------------------------
  // Data Polling
  // ---------------------------------------------------------------------------
  async function refreshData() {
    const [status, services, alerts, timeline] = await Promise.all([
      fetchJSON('/api/aref/status'),
      fetchJSON('/api/aref/services'),
      fetchJSON('/api/aref/alerts'),
      fetchJSON('/api/aref/timeline'),
    ]);

    if (status) {
      state.crs = status.crs || 0;
      state.pillars = status.pillars || state.pillars;
      state.maturity = status.maturity || {};
      state.chaosActive = status.chaos_active || false;
    }
    if (services) state.services = services;
    if (alerts) state.alerts = alerts.alerts || [];
    if (timeline) state.timeline = timeline.events || [];

    render();

    // Also refresh active section data
    const metricsSection = document.getElementById('section-metrics');
    if (metricsSection && metricsSection.style.display !== 'none') refreshMetrics();
    const detectionSection = document.getElementById('section-detection');
    if (detectionSection && detectionSection.style.display !== 'none') refreshDetection();
    const absorptionSection = document.getElementById('section-absorption');
    if (absorptionSection && absorptionSection.style.display !== 'none') refreshAbsorption();
    const adaptationSection = document.getElementById('section-adaptation');
    if (adaptationSection && adaptationSection.style.display !== 'none') refreshAdaptation();
    const recoverySection = document.getElementById('section-recovery');
    if (recoverySection && recoverySection.style.display !== 'none') refreshRecovery();
    const evolutionSection = document.getElementById('section-evolution');
    if (evolutionSection && evolutionSection.style.display !== 'none') refreshEvolution();
    const servicesSection = document.getElementById('section-services');
    if (servicesSection && servicesSection.style.display !== 'none') refreshServicesTab();
    const timelineSection = document.getElementById('section-timeline');
    if (timelineSection && timelineSection.style.display !== 'none') refreshTimelineTab();
  }

  // ---------------------------------------------------------------------------
  // CRS Gauge — build once, then transition attributes
  // ---------------------------------------------------------------------------
  function renderCRSGauge(score, maxScore = 5) {
    const el = document.getElementById('crs-gauge');
    if (!el) return;

    const pct = Math.min(score / maxScore, 1);
    const circumference = 2 * Math.PI * 80;
    const offset = circumference * (1 - pct);

    let color;
    if (score < 2) color = 'var(--crs-low)';
    else if (score < 3.5) color = 'var(--crs-mid)';
    else color = 'var(--crs-high)';

    if (!initialized.gauge) {
      // First render — build full markup
      el.innerHTML = `
        <svg viewBox="0 0 200 200">
          <circle class="crs-gauge-track" cx="100" cy="100" r="80"/>
          <circle class="crs-gauge-fill" cx="100" cy="100" r="80"
            stroke="${color}"
            stroke-dasharray="${circumference}"
            stroke-dashoffset="${circumference}"/>
        </svg>
        <div class="crs-gauge-label">
          <div class="crs-gauge-value" style="color:${color}" data-value="0">0.00</div>
          <div class="crs-gauge-subtitle">Composite Resilience Score</div>
        </div>
      `;
      // Trigger transition on next frame
      requestAnimationFrame(() => {
        const fill = el.querySelector('.crs-gauge-fill');
        if (fill) fill.setAttribute('stroke-dashoffset', offset);
        const valueEl = el.querySelector('.crs-gauge-value');
        if (valueEl) animateValue(valueEl, 0, score, 800);
      });
      initialized.gauge = true;
    } else {
      // Subsequent renders — transition existing elements
      const fill = el.querySelector('.crs-gauge-fill');
      const valueEl = el.querySelector('.crs-gauge-value');
      if (fill) {
        fill.setAttribute('stroke-dashoffset', offset);
        fill.setAttribute('stroke', color);
      }
      if (valueEl) {
        const oldVal = parseFloat(valueEl.getAttribute('data-value') || '0');
        valueEl.style.color = color;
        animateValue(valueEl, oldVal, score, 600);
      }
    }
    // Store current value for next diff
    const valueEl = el.querySelector('.crs-gauge-value');
    if (valueEl) valueEl.setAttribute('data-value', score);
  }

  // ---------------------------------------------------------------------------
  // Radar Chart — build once, morph the polygon and dots
  // ---------------------------------------------------------------------------
  function renderRadar(scores) {
    const el = document.getElementById('maturity-radar');
    if (!el) return;

    const cx = 200, cy = 200, maxR = 150, levels = 5;
    const angles = PILLAR_KEYS.map((_, i) => (i * 2 * Math.PI / PILLAR_KEYS.length) - Math.PI / 2);

    function computePoints(s) {
      return PILLAR_KEYS.map((p, i) => {
        const val = (s[p] || 1) / levels;
        const r = val * maxR;
        return `${cx + r * Math.cos(angles[i])},${cy + r * Math.sin(angles[i])}`;
      }).join(' ');
    }

    if (!initialized.radar) {
      // Build the full SVG structure once
      let bgPolygons = '';
      for (let lvl = levels; lvl >= 1; lvl--) {
        const r = (lvl / levels) * maxR;
        const points = angles.map(a => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`).join(' ');
        bgPolygons += `<polygon class="radar-polygon-bg" points="${points}"/>`;
      }

      let axes = angles.map(a =>
        `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${cx + maxR * Math.cos(a)}" y2="${cy + maxR * Math.sin(a)}"/>`
      ).join('');

      let dots = PILLAR_KEYS.map((p, i) => {
        const val = (scores[p] || 1) / levels;
        const r = val * maxR;
        return `<circle class="radar-dot" data-pillar="${p}" cx="${cx + r * Math.cos(angles[i])}" cy="${cy + r * Math.sin(angles[i])}" r="4" fill="${PILLAR_COLORS[p]}">
          <title>${PILLAR_LABELS[i]}: L${Math.round(scores[p] || 1)}</title>
        </circle>`;
      }).join('');

      let labelEls = PILLAR_KEYS.map((p, i) => {
        const lr = maxR + 30;
        const x = cx + lr * Math.cos(angles[i]);
        const y = cy + lr * Math.sin(angles[i]) + 4;
        return `<text class="radar-label" x="${x}" y="${y}" fill="${PILLAR_COLORS[p]}">${PILLAR_LABELS[i]}</text>`;
      }).join('');

      el.innerHTML = `
        <svg viewBox="0 0 400 400" class="maturity-radar">
          ${bgPolygons}
          ${axes}
          <polygon class="radar-polygon-value" points="${computePoints(scores)}"/>
          ${dots}
          ${labelEls}
        </svg>
      `;
      initialized.radar = true;
    } else {
      // Morph the value polygon and reposition dots
      const polygon = el.querySelector('.radar-polygon-value');
      if (polygon) polygon.setAttribute('points', computePoints(scores));

      PILLAR_KEYS.forEach((p, i) => {
        const dot = el.querySelector(`.radar-dot[data-pillar="${p}"]`);
        if (dot) {
          const val = (scores[p] || 1) / levels;
          const r = val * maxR;
          dot.setAttribute('cx', cx + r * Math.cos(angles[i]));
          dot.setAttribute('cy', cy + r * Math.sin(angles[i]));
          const title = dot.querySelector('title');
          if (title) title.textContent = `${PILLAR_LABELS[i]}: L${Math.round(scores[p] || 1)}`;
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Pillar Cards — build once, update text in place
  // ---------------------------------------------------------------------------
  function renderPillarCards() {
    const container = document.getElementById('pillar-cards');
    if (!container) return;

    const config = [
      { key: 'detection', label: 'Detection', icon: 'icon-detection', metric: 'MTTD', unit: 's', target: '< 300s' },
      { key: 'absorption', label: 'Absorption', icon: 'icon-absorption', metric: 'Containment', unit: '%', target: '> 95%' },
      { key: 'adaptation', label: 'Adaptation', icon: 'icon-adaptation', metric: 'Latency', unit: 's', target: '< 30s' },
      { key: 'recovery', label: 'Recovery', icon: 'icon-recovery', metric: 'MTTR', unit: 's', target: '< 900s' },
      { key: 'evolution', label: 'Evolution', icon: 'icon-evolution', metric: 'Velocity', unit: '/Q', target: '> 8/Q' },
    ];

    if (!initialized.pillarCards) {
      container.innerHTML = config.map(c => {
        const level = Math.round(state.pillars[c.key] || 1);
        return `
          <div class="card card--${c.key} card--glow animate-in" data-pillar="${c.key}">
            <div class="card-header">
              <div class="card-icon">
                <svg><use href="#${c.icon}"/></svg>
              </div>
              <span class="maturity-badge maturity-badge--l${level}" data-badge>L${level} ${LEVEL_NAMES[level]}</span>
            </div>
            <div class="card-title">${c.label}</div>
            <div class="card-value" data-card-value="${state.pillars[c.key] || 1}">${(state.pillars[c.key] || 1).toFixed(1)}</div>
            <div class="card-description">${c.metric} target: ${c.target}</div>
          </div>
        `;
      }).join('');
      initialized.pillarCards = true;
    } else {
      // Update only the values that changed
      config.forEach(c => {
        const card = container.querySelector(`[data-pillar="${c.key}"]`);
        if (!card) return;

        const valueEl = card.querySelector('.card-value');
        const badgeEl = card.querySelector('[data-badge]');
        const newVal = state.pillars[c.key] || 1;
        const oldVal = parseFloat(valueEl.getAttribute('data-card-value') || '1');
        const level = Math.round(newVal);

        if (Math.abs(oldVal - newVal) > 0.001) {
          animateValue(valueEl, oldVal, newVal, 500, 1);
          valueEl.setAttribute('data-card-value', newVal);
        }

        if (badgeEl) {
          const newBadge = `L${level} ${LEVEL_NAMES[level]}`;
          if (badgeEl.textContent !== newBadge) {
            badgeEl.textContent = newBadge;
            badgeEl.className = `maturity-badge maturity-badge--l${level}`;
          }
        }
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Service Status — build once, diff rows
  // ---------------------------------------------------------------------------
  function renderServices() {
    const container = document.getElementById('service-status');
    if (!container || !state.services.services) return;

    const entries = Object.entries(state.services.services);

    if (!initialized.services) {
      const rows = entries.map(([name, info]) => buildServiceRow(name, info)).join('');
      container.innerHTML = `
        <table class="data-table">
          <thead>
            <tr><th>Service</th><th>Status</th><th>Version</th><th>Last Check</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;
      initialized.services = true;
    } else {
      const tbody = container.querySelector('tbody');
      if (!tbody) return;

      entries.forEach(([name, info]) => {
        let row = tbody.querySelector(`tr[data-service="${name}"]`);
        if (!row) {
          // New service appeared — append
          tbody.insertAdjacentHTML('beforeend', buildServiceRow(name, info));
          return;
        }
        // Update existing row cells
        const cells = row.querySelectorAll('td');
        const healthy = info.status === 'healthy';
        const dot = cells[0].querySelector('.status-dot');
        if (dot) {
          dot.className = `status-dot ${healthy ? 'status-dot--healthy' : 'status-dot--critical status-dot--pulse'}`;
        }
        const statusCell = cells[1];
        if (statusCell && statusCell.textContent !== (info.status || 'unknown')) {
          statusCell.textContent = info.status || 'unknown';
          statusCell.style.transition = 'color 0.3s ease';
          statusCell.style.color = healthy ? 'var(--color-healthy)' : 'var(--color-critical)';
          setTimeout(() => { statusCell.style.color = ''; }, 600);
        }
        const timeCell = cells[3];
        if (timeCell && info.timestamp) {
          timeCell.textContent = new Date(info.timestamp * 1000).toLocaleTimeString();
        }
      });
    }
  }

  function buildServiceRow(name, info) {
    const healthy = info.status === 'healthy';
    const dotClass = healthy ? 'status-dot--healthy' : 'status-dot--critical status-dot--pulse';
    return `
      <tr data-service="${name}">
        <td>
          <div style="display:flex;align-items:center;gap:0.5rem">
            <span class="status-dot ${dotClass}"></span>
            <strong style="color:var(--text-primary)">${name}</strong>
          </div>
        </td>
        <td>${info.status || 'unknown'}</td>
        <td style="font-family:var(--font-mono)">${info.version || '-'}</td>
        <td>${info.timestamp ? new Date(info.timestamp * 1000).toLocaleTimeString() : '-'}</td>
      </tr>
    `;
  }

  // ---------------------------------------------------------------------------
  // Alerts — diff by content hash
  // ---------------------------------------------------------------------------
  let _lastAlertHash = '';

  function renderAlerts() {
    const container = document.getElementById('active-alerts');
    if (!container) return;

    // Simple content hash to avoid redundant redraws
    const hash = JSON.stringify(state.alerts.map(a => a.title + a.severity).slice(0, 10));
    if (hash === _lastAlertHash) return;
    _lastAlertHash = hash;

    if (!state.alerts.length) {
      if (!container.querySelector('.alerts-empty')) {
        container.style.opacity = '0';
        container.style.transition = 'opacity 0.3s ease';
        setTimeout(() => {
          container.innerHTML = `
            <div class="alerts-empty" style="text-align:center;padding:2rem;color:var(--text-muted)">
              <svg style="width:40px;height:40px;margin:0 auto 1rem;opacity:0.3"><use href="#icon-healthy"/></svg>
              <div>No active alerts</div>
            </div>
          `;
          container.style.opacity = '1';
        }, 150);
      }
      return;
    }

    // Cross-fade alert list
    container.style.opacity = '0';
    container.style.transition = 'opacity 0.3s ease';
    setTimeout(() => {
      container.innerHTML = state.alerts.slice(0, 10).map(a => `
        <div class="card alert-card" style="padding:0.75rem;margin-bottom:0.5rem;border-left:3px solid ${
          a.severity === 'critical' ? 'var(--color-critical)' :
          a.severity === 'emergency' ? 'var(--color-emergency)' :
          a.severity === 'warning' ? 'var(--color-warning)' : 'var(--color-info)'
        }">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <strong style="font-size:0.8125rem">${a.title || 'Alert'}</strong>
            <span class="header-badge badge-${a.severity === 'critical' || a.severity === 'emergency' ? 'critical' : 'warning'}">${a.severity}</span>
          </div>
          <div style="font-size:0.75rem;color:var(--text-muted);margin-top:0.25rem">${a.service || ''} &middot; ${a.detection_class || ''}</div>
        </div>
      `).join('');
      container.style.opacity = '1';
    }, 150);
  }

  // ---------------------------------------------------------------------------
  // Timeline — append new events, don't rebuild
  // ---------------------------------------------------------------------------
  let _lastTimelineLength = 0;

  function renderTimeline() {
    const container = document.getElementById('event-timeline');
    if (!container) return;

    const events = state.timeline.slice(-15).reverse();

    if (!initialized.timeline || !container.querySelector('.timeline')) {
      // First render
      container.innerHTML = `<div class="timeline">${
        events.map(e => buildTimelineEntry(e)).join('')
      }</div>`;
      _lastTimelineLength = state.timeline.length;
      initialized.timeline = true;
      return;
    }

    // Only update if new events arrived
    if (state.timeline.length === _lastTimelineLength) return;
    _lastTimelineLength = state.timeline.length;

    const timelineEl = container.querySelector('.timeline');
    if (!timelineEl) return;

    // Rebuild timeline but with a smooth cross-fade
    const newHtml = events.map(e => buildTimelineEntry(e)).join('');
    timelineEl.style.transition = 'opacity 0.25s ease';
    timelineEl.style.opacity = '0.4';
    setTimeout(() => {
      timelineEl.innerHTML = newHtml;
      timelineEl.style.opacity = '1';
    }, 150);
  }

  function buildTimelineEntry(e) {
    return `
      <div class="timeline-entry">
        <div class="timeline-dot timeline-dot--${e.category || 'detection'}"></div>
        <div class="timeline-time">${new Date(e.timestamp * 1000).toLocaleTimeString()}</div>
        <div class="timeline-title">${e.event_type || ''}</div>
        <div class="timeline-detail">${e.source || ''}</div>
      </div>
    `;
  }

  // ---------------------------------------------------------------------------
  // Metrics Tab — KPIs, Error Budgets, CRS Profiles, Weights, Pillar Scores
  // ---------------------------------------------------------------------------
  let metricsData = null;
  let metricsInitialized = false;

  const PROFILE_LABELS = {
    availability_critical: 'Availability Critical',
    data_integrity_critical: 'Data Integrity',
    balanced: 'Balanced',
    innovation_heavy: 'Innovation Heavy',
  };

  const PROFILE_COLORS = {
    availability_critical: '#3b82f6',
    data_integrity_critical: '#8b5cf6',
    balanced: '#38bdf8',
    innovation_heavy: '#ec4899',
  };

  async function refreshMetrics() {
    const data = await fetchJSON('/api/aref/metrics');
    if (data) {
      metricsData = data;
      renderMetrics();
    }
  }

  function renderMetrics() {
    if (!metricsData) return;
    const d = metricsData;

    // KPI Cards
    updateKPI('mttd', d.mttd, d.targets.mttd, 's', true);
    updateKPI('mttr', d.mttr, d.targets.mttr, 's', true);
    updateKPIAvailability(d.availability, d.targets.availability_slo);
    updateKPIIncidents(d.total_incidents);

    // Error Budgets
    renderErrorBudgets(d.error_budgets);

    // CRS by profile
    renderCRSProfiles(d.crs_profiles, d.current_profile);

    // Weight distribution
    renderWeightDistribution(d.crs_profiles, d.current_profile);

    // Pillar scores
    renderPillarScoresDetail(d.pillar_scores);
  }

  function updateKPI(key, value, target, unit, lowerIsBetter) {
    const card = document.querySelector(`.metrics-kpi[data-kpi="${key}"]`);
    if (!card) return;

    const valueEl = card.querySelector('[data-kpi-value]');
    const fillEl = card.querySelector('[data-kpi-fill]');
    const statusEl = card.querySelector('[data-kpi-status]');

    if (value === null || value === undefined) {
      if (valueEl) valueEl.textContent = '--';
      if (fillEl) fillEl.style.width = '0%';
      if (statusEl) statusEl.textContent = 'Awaiting incident data';
      return;
    }

    const displayVal = value >= 1 ? Math.round(value) + unit : value.toFixed(1) + unit;
    if (valueEl) {
      const oldText = valueEl.textContent;
      if (oldText !== displayVal) {
        const oldNum = parseFloat(oldText) || 0;
        animateValue(valueEl, oldNum, value, 600, value >= 1 ? 0 : 1);
        // append unit after animation settles
        setTimeout(() => { valueEl.textContent = displayVal; }, 650);
      }
    }

    // Bar: percentage of target consumed
    const pct = Math.min((value / target) * 100, 100);
    if (fillEl) fillEl.style.width = pct + '%';

    // Status text
    if (statusEl) {
      const withinTarget = lowerIsBetter ? value <= target : value >= target;
      statusEl.textContent = withinTarget
        ? `Within target (${target}${unit})`
        : `Exceeds target (${target}${unit})`;
      statusEl.style.color = withinTarget ? 'var(--color-healthy)' : 'var(--color-warning)';
    }
  }

  function updateKPIAvailability(value, slo) {
    const card = document.querySelector('.metrics-kpi[data-kpi="availability"]');
    if (!card) return;

    const valueEl = card.querySelector('[data-kpi-value]');
    const fillEl = card.querySelector('[data-kpi-fill]');
    const statusEl = card.querySelector('[data-kpi-status]');

    if (value === null || value === undefined) {
      if (valueEl) valueEl.textContent = '--';
      if (fillEl) fillEl.style.width = '0%';
      if (statusEl) statusEl.textContent = 'Awaiting uptime data';
      return;
    }

    const displayVal = value.toFixed(3) + '%';
    if (valueEl) valueEl.textContent = displayVal;
    if (fillEl) fillEl.style.width = Math.min(value, 100) + '%';

    const meetsSLO = value >= slo;
    if (statusEl) {
      statusEl.textContent = meetsSLO ? `Meets SLO (${slo}%)` : `Below SLO (${slo}%)`;
      statusEl.style.color = meetsSLO ? 'var(--color-healthy)' : 'var(--color-critical)';
    }
  }

  function updateKPIIncidents(count) {
    const card = document.querySelector('.metrics-kpi[data-kpi="incidents"]');
    if (!card) return;

    const valueEl = card.querySelector('[data-kpi-value]');
    if (valueEl) valueEl.textContent = count.toString();

    const fillEl = card.querySelector('[data-kpi-fill]');
    if (fillEl) fillEl.style.width = Math.min(count * 10, 100) + '%';
  }

  function renderErrorBudgets(budgets) {
    const container = document.getElementById('error-budgets-container');
    if (!container || !budgets) return;

    const html = Object.entries(budgets).map(([label, b]) => {
      const pct = b.remaining_pct;
      let barColor;
      if (pct > 60) barColor = 'var(--color-healthy)';
      else if (pct > 25) barColor = 'var(--color-warning)';
      else barColor = 'var(--color-critical)';

      const budgetStr = formatDuration(b.budget_total_seconds);
      const remainStr = formatDuration(b.remaining_seconds);

      return `
        <div class="eb-tier" data-eb="${label}">
          <div class="eb-tier-label">${label}</div>
          <div class="eb-tier-bar-wrap">
            <div class="eb-tier-bar">
              <div class="eb-tier-bar-fill" style="width:${pct}%;background:${barColor}" data-eb-fill>
                <span class="eb-tier-bar-text">${pct.toFixed(1)}%</span>
              </div>
            </div>
          </div>
          <div class="eb-tier-detail">${remainStr} / ${budgetStr}</div>
        </div>
      `;
    }).join('');

    if (!metricsInitialized) {
      container.innerHTML = html;
    } else {
      // Diff update: just update fill widths and text
      Object.entries(budgets).forEach(([label, b]) => {
        const row = container.querySelector(`[data-eb="${label}"]`);
        if (!row) { container.innerHTML = html; return; }
        const fill = row.querySelector('[data-eb-fill]');
        if (fill) {
          fill.style.width = b.remaining_pct + '%';
          const text = fill.querySelector('.eb-tier-bar-text');
          if (text) text.textContent = b.remaining_pct.toFixed(1) + '%';
        }
      });
    }
  }

  function renderCRSProfiles(profiles, currentProfile) {
    const container = document.getElementById('crs-profiles-container');
    if (!container || !profiles) return;

    const html = Object.entries(profiles).map(([key, p]) => {
      const pct = (p.crs / 5) * 100;
      const isActive = key === currentProfile;
      const color = PROFILE_COLORS[key] || 'var(--text-accent)';
      return `
        <div class="crs-profile-row ${isActive ? 'crs-profile-row--active' : ''}" data-profile="${key}">
          <div class="crs-profile-name">${PROFILE_LABELS[key] || key}</div>
          <div class="crs-profile-bar-wrap">
            <div class="crs-profile-bar">
              <div class="crs-profile-bar-fill" style="width:${pct}%;background:${color}" data-profile-fill>
                <span>${p.crs.toFixed(2)}</span>
              </div>
            </div>
          </div>
          <div class="crs-profile-score">${p.crs.toFixed(2)}</div>
        </div>
      `;
    }).join('');

    if (!metricsInitialized) {
      container.innerHTML = html;
    } else {
      // Update fill widths
      Object.entries(profiles).forEach(([key, p]) => {
        const row = container.querySelector(`[data-profile="${key}"]`);
        if (!row) { container.innerHTML = html; return; }
        const fill = row.querySelector('[data-profile-fill]');
        const scoreEl = row.querySelector('.crs-profile-score');
        if (fill) {
          fill.style.width = ((p.crs / 5) * 100) + '%';
          const inner = fill.querySelector('span');
          if (inner) inner.textContent = p.crs.toFixed(2);
        }
        if (scoreEl) scoreEl.textContent = p.crs.toFixed(2);
      });
    }
  }

  function renderWeightDistribution(profiles, currentProfile) {
    const container = document.getElementById('weight-distribution-chart');
    const label = document.getElementById('active-profile-label');
    if (!container || !profiles) return;

    const current = profiles[currentProfile];
    if (!current) return;

    if (label) label.textContent = PROFILE_LABELS[currentProfile] || currentProfile;

    const maxWeight = 0.35; // scale bar to max possible weight
    const html = PILLAR_KEYS.map((p, i) => {
      const w = current.weights[p] || 0;
      const pct = (w / maxWeight) * 100;
      return `
        <div class="weight-bar-row" data-weight-pillar="${p}">
          <div class="weight-bar-label" style="color:${PILLAR_COLORS[p]}">${PILLAR_LABELS[i]}</div>
          <div class="weight-bar-track">
            <div class="weight-bar-fill" style="width:${pct}%;background:${PILLAR_COLORS[p]}" data-weight-fill></div>
          </div>
          <div class="weight-bar-value">${(w * 100).toFixed(0)}%</div>
        </div>
      `;
    }).join('');

    if (!metricsInitialized) {
      container.innerHTML = html;
    } else {
      PILLAR_KEYS.forEach(p => {
        const row = container.querySelector(`[data-weight-pillar="${p}"]`);
        if (!row) { container.innerHTML = html; return; }
        const fill = row.querySelector('[data-weight-fill]');
        const w = current.weights[p] || 0;
        if (fill) fill.style.width = ((w / maxWeight) * 100) + '%';
        const valEl = row.querySelector('.weight-bar-value');
        if (valEl) valEl.textContent = (w * 100).toFixed(0) + '%';
      });
    }
  }

  function renderPillarScoresDetail(scores) {
    const container = document.getElementById('pillar-scores-detail');
    if (!container || !scores) return;

    const icons = {
      detection: { icon: 'icon-detection', bg: 'rgba(59,130,246,0.15)', fg: 'var(--color-detection)' },
      absorption: { icon: 'icon-absorption', bg: 'rgba(139,92,246,0.15)', fg: 'var(--color-absorption)' },
      adaptation: { icon: 'icon-adaptation', bg: 'rgba(245,158,11,0.15)', fg: 'var(--color-adaptation)' },
      recovery: { icon: 'icon-recovery', bg: 'rgba(16,185,129,0.15)', fg: 'var(--color-recovery)' },
      evolution: { icon: 'icon-evolution', bg: 'rgba(236,72,153,0.15)', fg: 'var(--color-evolution)' },
    };

    const html = PILLAR_KEYS.map((p, i) => {
      const score = scores[p] || 1;
      const pct = (score / 5) * 100;
      const level = Math.round(score);
      const ic = icons[p];
      return `
        <div class="pillar-score-row" data-ps="${p}">
          <div class="pillar-score-icon" style="background:${ic.bg};color:${ic.fg}">
            <svg><use href="#${ic.icon}"/></svg>
          </div>
          <div class="pillar-score-name">${PILLAR_LABELS[i]}</div>
          <div class="pillar-score-bar-wrap">
            <div class="pillar-score-bar">
              <div class="pillar-score-bar-fill" style="width:${pct}%;background:${PILLAR_COLORS[p]}" data-ps-fill></div>
            </div>
          </div>
          <div class="pillar-score-value">
            <span data-ps-score>${score.toFixed(1)}</span>
            <span class="maturity-badge maturity-badge--l${level}" style="font-size:0.6rem;padding:0.1rem 0.35rem">L${level}</span>
          </div>
        </div>
      `;
    }).join('');

    if (!metricsInitialized) {
      container.innerHTML = html;
    } else {
      PILLAR_KEYS.forEach(p => {
        const row = container.querySelector(`[data-ps="${p}"]`);
        if (!row) { container.innerHTML = html; return; }
        const score = scores[p] || 1;
        const fill = row.querySelector('[data-ps-fill]');
        if (fill) fill.style.width = ((score / 5) * 100) + '%';
        const scoreEl = row.querySelector('[data-ps-score]');
        if (scoreEl) scoreEl.textContent = score.toFixed(1);
      });
    }

    metricsInitialized = true;
  }

  function formatDuration(seconds) {
    if (seconds >= 86400) return (seconds / 86400).toFixed(1) + 'd';
    if (seconds >= 3600) return (seconds / 3600).toFixed(1) + 'h';
    if (seconds >= 60) return (seconds / 60).toFixed(1) + 'm';
    return seconds.toFixed(0) + 's';
  }

  // Expose for the refresh button
  window.refreshMetrics = refreshMetrics;

  // ---------------------------------------------------------------------------
  // Detection Tab
  // ---------------------------------------------------------------------------
  let detectionData = null;
  let detectionInitialized = false;

  async function refreshDetection() {
    const data = await fetchJSON('/api/aref/detection');
    if (data && data.status !== undefined) {
      detectionData = data;
      renderDetection();
    }
  }

  function renderDetection() {
    if (!detectionData) return;
    const d = detectionData;

    // Engine status badge
    const statusEl = document.getElementById('detection-engine-status');
    if (statusEl) {
      const running = d.status === 'running';
      statusEl.className = `header-badge ${running ? 'badge-healthy' : 'badge-critical'}`;
      statusEl.textContent = running ? 'RUNNING' : 'STOPPED';
    }

    // Summary cards
    const alerts = d.alerts || {};
    updateDetCard('total', alerts.total_alerts || 0, alerts.total_alerts > 0 ? `${alerts.active_alerts} active` : 'No alerts fired');
    updateDetCard('active', alerts.active_alerts || 0, alerts.active_alerts > 0 ? 'Requires attention' : 'All clear');
    updateDetCard('weekly', alerts.weekly_count || 0, `Fatigue threshold: ${alerts.fatigue_threshold || 50}`);

    // Weekly fatigue bar
    const fatigueMax = alerts.fatigue_threshold || 50;
    const fatiguePct = Math.min(((alerts.weekly_count || 0) / fatigueMax) * 100, 100);
    const fatigueFill = document.querySelector('[data-det-fatigue-fill]');
    if (fatigueFill) {
      fatigueFill.style.width = fatiguePct + '%';
      fatigueFill.style.background = fatiguePct > 80 ? 'var(--color-critical)' : fatiguePct > 50 ? 'var(--color-warning)' : 'var(--color-healthy)';
    }

    // Alert-to-action ratio
    const ratio = alerts.alert_to_action_ratio;
    const ratioEl = document.querySelector('[data-det-value="ratio"]');
    if (ratioEl) ratioEl.textContent = ratio !== undefined && ratio > 0 ? ratio.toFixed(1) + ':1' : '--';
    const ratioSub = document.querySelector('[data-det-sub="ratio"]');
    if (ratioSub) {
      const target = d.config?.alert_to_action_target || 3;
      ratioSub.textContent = ratio > 0 && ratio <= target ? 'Healthy signal ratio' : 'Signal-to-noise ratio';
    }

    // Threshold monitors
    renderThresholdMonitors(d.threshold);

    // Anomaly streams
    renderAnomalyStreams(d.anomaly);

    // Synthetic probes
    renderSyntheticProbes(d.synthetic);

    // SLI/SLO
    renderSLITracking(d.sli_tracker);

    // Active alerts table
    renderDetAlerts(d.active_alerts || []);

    // Config grid
    renderDetConfig(d.config);

    detectionInitialized = true;
  }

  function updateDetCard(key, value, subtitle) {
    const valEl = document.querySelector(`[data-det-value="${key}"]`);
    const subEl = document.querySelector(`[data-det-sub="${key}"]`);
    if (valEl) valEl.textContent = value.toString();
    if (subEl) subEl.textContent = subtitle;
  }

  function renderThresholdMonitors(threshold) {
    const container = document.getElementById('det-threshold-container');
    const empty = document.getElementById('det-threshold-empty');
    const countEl = document.querySelector('[data-det-threshold-count]');
    if (!container) return;

    const rules = threshold?.rules || [];
    if (countEl) countEl.textContent = `${rules.length} rule${rules.length !== 1 ? 's' : ''}`;

    if (rules.length === 0) {
      container.innerHTML = '';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';

    container.innerHTML = rules.map(r => {
      const breaching = r.breach_count > 0;
      const dotColor = breaching ? 'var(--color-warning)' : 'var(--color-healthy)';
      return `
        <div class="det-row">
          <div class="det-row-icon" style="background:${dotColor};box-shadow:0 0 4px ${dotColor}"></div>
          <div class="det-row-name">${r.name}</div>
          <div class="det-row-service">${r.service}</div>
          <div class="det-row-value">${r.last_value !== null ? r.last_value.toFixed(2) : '--'}</div>
          <div class="det-row-bar">
            <div class="progress-bar"><div class="progress-bar-fill" style="width:${Math.min(r.breach_count * 33, 100)}%;background:${dotColor}"></div></div>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderAnomalyStreams(anomaly) {
    const container = document.getElementById('det-anomaly-container');
    const empty = document.getElementById('det-anomaly-empty');
    const countEl = document.querySelector('[data-det-anomaly-count]');
    if (!container) return;

    const streams = anomaly ? Object.entries(anomaly) : [];
    if (countEl) countEl.textContent = `${streams.length} stream${streams.length !== 1 ? 's' : ''}`;

    if (streams.length === 0) {
      container.innerHTML = '';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';

    container.innerHTML = streams.map(([key, s]) => {
      const anomalous = s.z_score > 3.0;
      const dotColor = anomalous ? 'var(--color-critical)' : s.z_score > 2.0 ? 'var(--color-warning)' : 'var(--color-healthy)';
      return `
        <div class="det-row" style="flex-wrap:wrap">
          <div class="det-row-icon" style="background:${dotColor};box-shadow:0 0 4px ${dotColor}"></div>
          <div class="det-row-name">${key}</div>
          <div class="det-stream-stats">
            <div class="det-stream-stat">
              <span class="det-stream-stat-label">Latest</span>
              <span class="det-stream-stat-value">${s.latest !== null ? s.latest.toFixed(2) : '--'}</span>
            </div>
            <div class="det-stream-stat">
              <span class="det-stream-stat-label">Mean</span>
              <span class="det-stream-stat-value">${s.mean.toFixed(2)}</span>
            </div>
            <div class="det-stream-stat">
              <span class="det-stream-stat-label">Std</span>
              <span class="det-stream-stat-value">${s.std.toFixed(2)}</span>
            </div>
            <div class="det-stream-stat">
              <span class="det-stream-stat-label">Z-Score</span>
              <span class="det-stream-stat-value" style="color:${dotColor}">${s.z_score.toFixed(1)}&sigma;</span>
            </div>
            <div class="det-stream-stat">
              <span class="det-stream-stat-label">Samples</span>
              <span class="det-stream-stat-value">${s.samples}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  function renderSyntheticProbes(synthetic) {
    const container = document.getElementById('det-synthetic-container');
    const empty = document.getElementById('det-synthetic-empty');
    const countEl = document.querySelector('[data-det-probe-count]');
    if (!container) return;

    const targets = synthetic?.targets || [];
    if (countEl) countEl.textContent = `${targets.length} target${targets.length !== 1 ? 's' : ''}`;

    if (targets.length === 0) {
      container.innerHTML = '';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';

    container.innerHTML = targets.map(t => {
      const healthy = t.last_status === 'healthy';
      const dotColor = healthy ? 'var(--color-healthy)' : 'var(--color-critical)';
      return `
        <div class="det-row">
          <div class="det-row-icon" style="background:${dotColor};box-shadow:0 0 4px ${dotColor}"></div>
          <div class="det-row-name">${t.service}</div>
          <div class="det-row-service">${t.url}</div>
          <div class="det-probe-status">
            <span style="color:${dotColor}">${t.last_status || 'unknown'}</span>
          </div>
          <div class="det-row-value">${t.last_latency_ms > 0 ? t.last_latency_ms.toFixed(0) + 'ms' : '--'}</div>
        </div>
      `;
    }).join('');
  }

  function renderSLITracking(tracker) {
    const container = document.getElementById('det-sli-container');
    const empty = document.getElementById('det-sli-empty');
    const countEl = document.querySelector('[data-det-sli-count]');
    if (!container) return;

    const slis = tracker?.slis_tracked || 0;
    const slos = tracker?.slos_defined || 0;
    if (countEl) countEl.textContent = `${slis} SLI${slis !== 1 ? 's' : ''} / ${slos} SLO${slos !== 1 ? 's' : ''}`;

    const budgets = tracker?.budgets ? Object.entries(tracker.budgets) : [];

    if (budgets.length === 0) {
      container.innerHTML = '';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';

    container.innerHTML = budgets.map(([key, b]) => {
      const pct = 100 - b.consumed_pct;
      let barColor;
      if (pct > 60) barColor = 'var(--color-healthy)';
      else if (pct > 25) barColor = 'var(--color-warning)';
      else barColor = 'var(--color-critical)';

      return `
        <div class="eb-tier">
          <div class="eb-tier-label" style="width:auto;font-size:0.75rem">${b.service}/${b.slo}</div>
          <div class="eb-tier-bar-wrap">
            <div class="eb-tier-bar">
              <div class="eb-tier-bar-fill" style="width:${pct}%;background:${barColor}">
                <span class="eb-tier-bar-text">${pct.toFixed(1)}%</span>
              </div>
            </div>
          </div>
          <div class="eb-tier-detail">${(b.target * 100).toFixed(1)}% SLO</div>
        </div>
      `;
    }).join('');
  }

  function renderDetAlerts(alerts) {
    const container = document.getElementById('det-alerts-table');
    if (!container) return;

    if (!alerts.length) {
      container.innerHTML = `
        <div style="text-align:center;padding:var(--space-lg);color:var(--text-muted);font-size:0.8125rem">
          <svg style="width:32px;height:32px;opacity:0.2;margin:0 auto var(--space-sm)"><use href="#icon-healthy"/></svg>
          <div>No active alerts</div>
        </div>
      `;
      return;
    }

    const rows = alerts.map(a => `
      <tr>
        <td><span class="det-severity det-severity--${a.severity}">${a.severity}</span></td>
        <td><strong style="color:var(--text-primary)">${a.title}</strong></td>
        <td style="font-family:var(--font-mono)">${a.service}</td>
        <td><span class="maturity-badge maturity-badge--l${a.detection_class === 'threshold' ? '2' : a.detection_class === 'anomaly' ? '3' : '1'}" style="font-size:0.65rem">${a.detection_class}</span></td>
        <td style="font-family:var(--font-mono);font-size:0.75rem">${new Date(a.fired_at * 1000).toLocaleTimeString()}</td>
        <td style="font-family:var(--font-mono);font-size:0.75rem">${a.alert_id}</td>
      </tr>
    `).join('');

    container.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Severity</th><th>Title</th><th>Service</th><th>Class</th><th>Fired</th><th>ID</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderDetConfig(config) {
    const container = document.getElementById('det-config-grid');
    if (!container || !config) return;

    const items = [
      { label: 'MTTD Target', value: config.mttd_target + 's', desc: '< 5 minutes' },
      { label: 'Threshold Interval', value: config.threshold_interval + 's', desc: 'Check frequency' },
      { label: 'Anomaly Interval', value: config.anomaly_interval + 's', desc: 'ML scan cycle' },
      { label: 'Probe Interval', value: config.synthetic_interval + 's', desc: 'Health check cycle' },
      { label: 'Fatigue Limit', value: config.fatigue_max_weekly + '/wk', desc: 'Max alerts/week' },
      { label: 'Alert:Action Target', value: config.alert_to_action_target + ':1', desc: 'Signal ratio' },
      { label: 'Correlation Window', value: formatDuration(config.correlation_window), desc: 'Change correlation' },
    ];

    const html = items.map(item => `
      <div class="det-config-item">
        <div class="det-config-label">${item.label}</div>
        <div class="det-config-value">${item.value}</div>
        <div style="font-size:0.65rem;color:var(--text-muted);margin-top:2px">${item.desc}</div>
      </div>
    `).join('');

    if (!detectionInitialized) {
      container.innerHTML = html;
    }
    // Config is static, no need to diff update
  }

  window.refreshDetection = refreshDetection;

  // ---------------------------------------------------------------------------
  // Absorption Tab
  // ---------------------------------------------------------------------------
  let absorptionData = null;
  let absorptionInitialized = false;

  async function refreshAbsorption() {
    const data = await fetchJSON('/api/aref/absorption');
    if (data && data.circuit_breakers !== undefined) {
      absorptionData = data;
      renderAbsorption();
    }
  }

  function renderAbsorption() {
    if (!absorptionData) return;
    const d = absorptionData;

    const cb = d.circuit_breakers || {};
    const rl = d.rate_limiters || {};
    const bh = d.bulkheads || {};
    const deg = d.degradation || {};

    // Summary cards
    updateAbsCard('breakers', cb.total || 0, `${cb.open || 0} open`);
    updateAbsCard('open', cb.open || 0, cb.open > 0 ? 'Failures contained' : 'All circuits closed');
    updateAbsCard('limiters', rl.total || 0, `Token bucket instances`);
    updateAbsCard('bulkheads', bh.total || 0, `Resource partitions`);

    // Circuit breakers
    renderCircuitBreakers(cb);

    // Rate limiters
    renderRateLimiters(rl);

    // Bulkheads
    renderBulkheads(bh);

    // Degradation
    renderDegradation(deg);

    // Blast radius
    renderBlastRadius(d.blast_radius || {});

    // Config
    renderAbsConfig(d.config);

    absorptionInitialized = true;
  }

  function updateAbsCard(key, value, subtitle) {
    const valEl = document.querySelector(`[data-abs-value="${key}"]`);
    const subEl = document.querySelector(`[data-abs-sub="${key}"]`);
    if (valEl) valEl.textContent = value.toString();
    if (subEl) subEl.textContent = subtitle;
  }

  function cbStateColor(state) {
    if (state === 'CLOSED') return 'var(--color-healthy)';
    if (state === 'OPEN') return 'var(--color-critical)';
    if (state === 'HALF_OPEN') return 'var(--color-warning)';
    return 'var(--text-muted)';
  }

  function renderCircuitBreakers(cb) {
    const container = document.getElementById('abs-cb-container');
    const countEl = document.querySelector('[data-abs-cb-count]');
    if (!container) return;

    const breakers = cb.breakers ? Object.entries(cb.breakers) : [];
    if (countEl) countEl.textContent = `${breakers.length} breaker${breakers.length !== 1 ? 's' : ''}`;

    if (breakers.length === 0) {
      container.innerHTML = '<div class="abs-empty">No circuit breakers registered</div>';
      return;
    }

    container.innerHTML = breakers.map(([name, b]) => {
      const color = cbStateColor(b.state);
      const failPct = Math.min((b.failure_count / b.failure_threshold) * 100, 100);
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${color};box-shadow:0 0 6px ${color}"></div>
          <div class="abs-row-name">${b.service}<span class="abs-row-arrow">&rarr;</span>${b.dependency}</div>
          <div class="abs-row-badge abs-state abs-state--${b.state.toLowerCase()}">${b.state}</div>
          <div class="abs-row-bar">
            <div class="progress-bar"><div class="progress-bar-fill" style="width:${failPct}%;background:${color}"></div></div>
          </div>
          <div class="abs-row-stat">${b.failure_count}/${b.failure_threshold}</div>
          <div class="abs-row-stat abs-row-stat--blocked">${b.total_blocked} blocked</div>
        </div>
      `;
    }).join('');
  }

  function renderRateLimiters(rl) {
    const container = document.getElementById('abs-rl-container');
    const countEl = document.querySelector('[data-abs-rl-count]');
    if (!container) return;

    const limiters = rl.limiters ? Object.entries(rl.limiters) : [];
    if (countEl) countEl.textContent = `${limiters.length} limiter${limiters.length !== 1 ? 's' : ''}`;

    if (limiters.length === 0) {
      container.innerHTML = '<div class="abs-empty">No rate limiters configured</div>';
      return;
    }

    container.innerHTML = limiters.map(([name, l]) => {
      const tokenPct = Math.min((l.available_tokens / l.burst_capacity) * 100, 100);
      const tokenColor = tokenPct > 50 ? 'var(--color-healthy)' : tokenPct > 20 ? 'var(--color-warning)' : 'var(--color-critical)';
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${tokenColor};box-shadow:0 0 6px ${tokenColor}"></div>
          <div class="abs-row-name">${name}</div>
          <div class="abs-row-stats">
            <div class="abs-stat-pair"><span class="abs-stat-label">Rate</span><span class="abs-stat-value">${l.rate_per_second}/s</span></div>
            <div class="abs-stat-pair"><span class="abs-stat-label">Burst</span><span class="abs-stat-value">${l.burst_capacity}</span></div>
            <div class="abs-stat-pair"><span class="abs-stat-label">Tokens</span><span class="abs-stat-value" style="color:${tokenColor}">${l.available_tokens.toFixed(0)}</span></div>
          </div>
          <div class="abs-row-bar">
            <div class="progress-bar"><div class="progress-bar-fill" style="width:${tokenPct}%;background:${tokenColor}"></div></div>
          </div>
          <div class="abs-row-stat">${l.total_allowed} ok</div>
          <div class="abs-row-stat abs-row-stat--blocked">${l.total_rejected} rej</div>
        </div>
      `;
    }).join('');
  }

  function renderBulkheads(bh) {
    const container = document.getElementById('abs-bh-container');
    const countEl = document.querySelector('[data-abs-bh-count]');
    if (!container) return;

    const partitions = bh.partitions ? Object.entries(bh.partitions) : [];
    if (countEl) countEl.textContent = `${partitions.length} partition${partitions.length !== 1 ? 's' : ''}`;

    if (partitions.length === 0) {
      container.innerHTML = '<div class="abs-empty">No bulkheads configured</div>';
      return;
    }

    container.innerHTML = partitions.map(([name, b]) => {
      const util = b.utilization_pct || 0;
      const utilColor = util > 80 ? 'var(--color-critical)' : util > 50 ? 'var(--color-warning)' : 'var(--color-healthy)';
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${utilColor};box-shadow:0 0 6px ${utilColor}"></div>
          <div class="abs-row-name">${name}</div>
          <div class="abs-row-stats">
            <div class="abs-stat-pair"><span class="abs-stat-label">Active</span><span class="abs-stat-value">${b.active}/${b.max_concurrent}</span></div>
            <div class="abs-stat-pair"><span class="abs-stat-label">Queued</span><span class="abs-stat-value">${b.queued}</span></div>
            <div class="abs-stat-pair"><span class="abs-stat-label">Util</span><span class="abs-stat-value" style="color:${utilColor}">${util.toFixed(0)}%</span></div>
          </div>
          <div class="abs-row-bar">
            <div class="progress-bar"><div class="progress-bar-fill" style="width:${util}%;background:${utilColor}"></div></div>
          </div>
          <div class="abs-row-stat">${b.total_calls} calls</div>
          <div class="abs-row-stat abs-row-stat--blocked">${b.rejected} rej</div>
        </div>
      `;
    }).join('');
  }

  function renderDegradation(deg) {
    const container = document.getElementById('abs-deg-container');
    const countEl = document.querySelector('[data-abs-deg-count]');
    if (!container) return;

    const svcs = Object.entries(deg);
    if (countEl) countEl.textContent = `${svcs.length} service${svcs.length !== 1 ? 's' : ''}`;

    if (svcs.length === 0) {
      container.innerHTML = '<div class="abs-empty">No degradation tiers configured</div>';
      return;
    }

    const levelColors = { 'FULL': 'var(--color-healthy)', 'REDUCED': 'var(--color-warning)', 'MINIMAL': 'var(--color-critical)', 'EMERGENCY': '#dc2626' };
    const levelIcons = { 'FULL': '4', 'REDUCED': '3', 'MINIMAL': '2', 'EMERGENCY': '1' };

    container.innerHTML = svcs.map(([svc, d]) => {
      const color = levelColors[d.current_level] || 'var(--text-muted)';
      const tiersDefined = d.tiers_defined || 0;
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${color};box-shadow:0 0 6px ${color}"></div>
          <div class="abs-row-name">${svc}</div>
          <div class="abs-row-badge abs-deg-level" style="border-color:${color};color:${color}">${d.current_level}</div>
          <div class="abs-deg-tiers">
            ${['FULL','REDUCED','MINIMAL','EMERGENCY'].map(lv => {
              const active = d.current_level === lv;
              return `<div class="abs-deg-pip ${active ? 'abs-deg-pip--active' : ''}" style="${active ? 'background:' + color : ''}" title="${lv}"></div>`;
            }).join('')}
          </div>
          <div class="abs-row-stat">${tiersDefined} tiers</div>
          <div class="abs-row-stat">${d.changes} changes</div>
        </div>
      `;
    }).join('');
  }

  function renderBlastRadius(graph) {
    const container = document.getElementById('abs-blast-container');
    if (!container) return;

    const nodes = Object.entries(graph);
    if (nodes.length === 0) {
      container.innerHTML = '<div class="abs-empty">No dependency graph registered</div>';
      return;
    }

    // Render as a node grid with dependency arrows
    container.innerHTML = `
      <div class="abs-blast-grid">
        ${nodes.map(([name, n]) => {
          const critColor = n.criticality === 'critical' ? 'var(--color-critical)' :
                            n.criticality === 'high' ? 'var(--color-warning)' : 'var(--color-healthy)';
          const typeIcon = n.type === 'database' ? '#icon-metrics' :
                           n.type === 'cache' ? '#icon-evolution' : '#icon-service';
          return `
            <div class="abs-blast-node" style="border-color:${critColor}">
              <div class="abs-blast-node-header">
                <svg class="abs-blast-node-icon"><use href="${typeIcon}"/></svg>
                <div class="abs-blast-node-name">${name}</div>
                <div class="abs-blast-node-type">${n.type}</div>
              </div>
              <div class="abs-blast-node-crit" style="color:${critColor}">${n.criticality}</div>
              ${n.dependencies.length > 0 ? `
                <div class="abs-blast-deps">
                  <span class="abs-stat-label">Depends on:</span>
                  ${n.dependencies.map(d => `<span class="abs-blast-dep-tag">${d}</span>`).join('')}
                </div>
              ` : ''}
              ${n.dependents.length > 0 ? `
                <div class="abs-blast-deps">
                  <span class="abs-stat-label">Depended by:</span>
                  ${n.dependents.map(d => `<span class="abs-blast-dep-tag abs-blast-dep-tag--rev">${d}</span>`).join('')}
                </div>
              ` : ''}
              ${n.failure_modes.length > 0 ? `
                <div class="abs-blast-modes">
                  ${n.failure_modes.map(m => `<span class="abs-blast-mode">${m}</span>`).join('')}
                </div>
              ` : ''}
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  function renderAbsConfig(config) {
    const container = document.getElementById('abs-config-grid');
    if (!container || !config) return;

    const items = [
      { label: 'Blast Radius Target', value: config.blast_radius_target_pct + '%', desc: 'Containment ≥ 95%' },
      { label: 'CB Failure Threshold', value: config.circuit_breaker_failure_threshold, desc: 'Consecutive failures to open' },
      { label: 'CB Recovery Timeout', value: config.circuit_breaker_recovery_timeout + 's', desc: 'OPEN → HALF_OPEN' },
      { label: 'Bulkhead Max Concurrent', value: config.bulkhead_max_concurrent, desc: 'Per-partition limit' },
      { label: 'Rate Limit', value: config.rate_limit_rps + '/s', desc: 'Requests per second' },
      { label: 'Burst Capacity', value: config.rate_limit_burst, desc: 'Token bucket size' },
    ];

    if (!absorptionInitialized) {
      container.innerHTML = items.map(item => `
        <div class="det-config-item">
          <div class="det-config-label">${item.label}</div>
          <div class="det-config-value">${item.value}</div>
          <div style="font-size:0.65rem;color:var(--text-muted);margin-top:2px">${item.desc}</div>
        </div>
      `).join('');
    }
  }

  window.refreshAbsorption = refreshAbsorption;

  // ---------------------------------------------------------------------------
  // Adaptation Tab
  // ---------------------------------------------------------------------------
  let adaptationData = null;
  let adaptationInitialized = false;

  async function refreshAdaptation() {
    const data = await fetchJSON('/api/aref/adaptation');
    if (data && data.feature_flags !== undefined) {
      adaptationData = data;
      renderAdaptation();
    }
  }

  function renderAdaptation() {
    if (!adaptationData) return;
    const d = adaptationData;

    const ff = d.feature_flags || {};
    const ts = d.traffic_shifter || {};
    const sc = d.scaler || {};

    // Summary cards
    updateAdpCard('active', d.active_adaptations || 0,
      d.active_adaptations > 0 ? 'Strategies executing' : 'No active adaptations');
    updateAdpCard('total', d.total_adaptations || 0,
      d.total_adaptations > 0 ? `${(d.adaptation_history || []).filter(h => h.status === 'completed').length} completed` : 'No history');
    updateAdpCard('flags', ff.total || 0,
      `${ff.enabled || 0} enabled / ${ff.disabled || 0} disabled`);

    const totalInstances = sc.instances ? Object.values(sc.instances).reduce((a, b) => a + b, 0) : 0;
    updateAdpCard('instances', totalInstances,
      `Across ${sc.instances ? Object.keys(sc.instances).length : 0} services`);

    renderFeatureFlags(ff);
    renderAutoScaler(sc);
    renderTrafficRouting(ts);
    renderDecisionTree(d.decision_tree_strategies || {});
    renderAdaptationHistory(d.adaptation_history || []);
    renderAdpConfig(d.config);

    adaptationInitialized = true;
  }

  function updateAdpCard(key, value, subtitle) {
    const valEl = document.querySelector(`[data-adp-value="${key}"]`);
    const subEl = document.querySelector(`[data-adp-sub="${key}"]`);
    if (valEl) valEl.textContent = value.toString();
    if (subEl) subEl.textContent = subtitle;
  }

  function renderFeatureFlags(ff) {
    const container = document.getElementById('adp-ff-container');
    const countEl = document.querySelector('[data-adp-ff-count]');
    if (!container) return;

    const flags = ff.flags ? Object.entries(ff.flags) : [];
    if (countEl) countEl.textContent = `${flags.length} flag${flags.length !== 1 ? 's' : ''}`;

    if (flags.length === 0) {
      container.innerHTML = '<div class="abs-empty">No feature flags registered</div>';
      return;
    }

    container.innerHTML = flags.map(([name, f]) => {
      const color = f.enabled ? 'var(--color-healthy)' : 'var(--color-critical)';
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${color};box-shadow:0 0 6px ${color}"></div>
          <div class="abs-row-name">${name}</div>
          <div class="abs-row-badge ${f.enabled ? 'abs-state--closed' : 'abs-state--open'}">${f.enabled ? 'ON' : 'OFF'}</div>
          ${f.critical ? '<div class="adp-flag-crit">CRITICAL</div>' : ''}
          <div class="abs-row-stat">${f.service}</div>
        </div>
      `;
    }).join('');
  }

  function renderAutoScaler(sc) {
    const container = document.getElementById('adp-sc-container');
    const countEl = document.querySelector('[data-adp-sc-count]');
    if (!container) return;

    const instances = sc.instances ? Object.entries(sc.instances) : [];
    const limits = sc.limits || {};
    if (countEl) countEl.textContent = `${instances.length} service${instances.length !== 1 ? 's' : ''}`;

    if (instances.length === 0) {
      container.innerHTML = '<div class="abs-empty">No services registered for scaling</div>';
      return;
    }

    container.innerHTML = instances.map(([svc, count]) => {
      const lim = limits[svc] || { min: 1, max: 10 };
      const pct = ((count - lim.min) / (lim.max - lim.min)) * 100;
      const color = pct > 80 ? 'var(--color-critical)' : pct > 50 ? 'var(--color-warning)' : 'var(--color-healthy)';
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${color};box-shadow:0 0 6px ${color}"></div>
          <div class="abs-row-name">${svc}</div>
          <div class="abs-row-stats">
            <div class="abs-stat-pair"><span class="abs-stat-label">Current</span><span class="abs-stat-value">${count}</span></div>
            <div class="abs-stat-pair"><span class="abs-stat-label">Min</span><span class="abs-stat-value">${lim.min}</span></div>
            <div class="abs-stat-pair"><span class="abs-stat-label">Max</span><span class="abs-stat-value">${lim.max}</span></div>
          </div>
          <div class="abs-row-bar">
            <div class="progress-bar"><div class="progress-bar-fill" style="width:${pct}%;background:${color}"></div></div>
          </div>
          <div class="abs-row-stat">${count}/${lim.max}</div>
        </div>
      `;
    }).join('');

    // Scaling history
    const history = sc.scaling_history || [];
    if (history.length > 0) {
      container.innerHTML += `
        <div style="margin-top:var(--space-md);padding-top:var(--space-sm);border-top:1px solid var(--border-default)">
          <div class="abs-stat-label" style="margin-bottom:var(--space-xs)">Recent Scaling Events</div>
          ${history.slice(-5).reverse().map(h => `
            <div class="adp-history-mini">
              <span class="adp-history-dir adp-history-dir--${h.direction}">${h.direction === 'up' ? '&#9650;' : '&#9660;'}</span>
              <span>${h.service}</span>
              <span class="abs-row-stat">${h.old_count} &rarr; ${h.new_count}</span>
            </div>
          `).join('')}
        </div>
      `;
    }
  }

  function renderTrafficRouting(ts) {
    const container = document.getElementById('adp-ts-container');
    const countEl = document.querySelector('[data-adp-ts-count]');
    if (!container) return;

    const svcs = ts.services ? Object.entries(ts.services) : [];
    if (countEl) countEl.textContent = `${svcs.length} service${svcs.length !== 1 ? 's' : ''}`;

    if (svcs.length === 0) {
      container.innerHTML = '<div class="abs-empty">No traffic routes registered</div>';
      return;
    }

    container.innerHTML = svcs.map(([svc, routes]) => {
      return `
        <div class="adp-traffic-svc">
          <div class="adp-traffic-svc-name">${svc}</div>
          <div class="adp-traffic-routes">
            ${routes.map(r => {
              const color = !r.healthy ? 'var(--color-critical)' : r.weight > 0 ? 'var(--color-healthy)' : 'var(--text-muted)';
              return `
                <div class="adp-traffic-route">
                  <div class="abs-row-state" style="background:${color};box-shadow:0 0 4px ${color}"></div>
                  <div class="adp-traffic-target">${r.target}</div>
                  <div class="adp-traffic-weight-bar">
                    <div class="progress-bar"><div class="progress-bar-fill" style="width:${r.weight}%;background:${color}"></div></div>
                  </div>
                  <div class="adp-traffic-weight">${r.weight}%</div>
                  <div class="abs-row-badge ${r.healthy ? 'abs-state--closed' : 'abs-state--open'}" style="font-size:0.6rem">${r.healthy ? 'HEALTHY' : 'DOWN'}</div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }).join('');

    // Shift history
    const history = ts.shift_history || [];
    if (history.length > 0) {
      container.innerHTML += `
        <div style="margin-top:var(--space-md);padding-top:var(--space-sm);border-top:1px solid var(--border-default)">
          <div class="abs-stat-label" style="margin-bottom:var(--space-xs)">Recent Shifts</div>
          ${history.slice(-5).reverse().map(h => `
            <div class="adp-history-mini">
              <span>${h.from}</span>
              <span style="color:var(--text-muted)">&rarr;</span>
              <span>${h.to}</span>
              <span class="abs-row-stat">${h.weight}%</span>
            </div>
          `).join('')}
        </div>
      `;
    }
  }

  function renderDecisionTree(strategies) {
    const container = document.getElementById('adp-dt-container');
    if (!container) return;

    const entries = Object.entries(strategies);
    if (entries.length === 0) {
      container.innerHTML = '<div class="abs-empty">No strategies loaded</div>';
      return;
    }

    const riskColors = { 'low': 'var(--color-healthy)', 'medium': 'var(--color-warning)', 'high': 'var(--color-critical)' };

    container.innerHTML = entries.map(([strategy, risk]) => {
      const color = riskColors[risk] || 'var(--text-muted)';
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${color};box-shadow:0 0 6px ${color}"></div>
          <div class="abs-row-name">${strategy.replace(/_/g, ' ')}</div>
          <div class="abs-row-badge" style="border:1px solid ${color};color:${color};background:transparent">${risk} risk</div>
        </div>
      `;
    }).join('');
  }

  function renderAdaptationHistory(history) {
    const container = document.getElementById('adp-history-table');
    if (!container) return;

    if (!history.length) {
      container.innerHTML = `
        <div style="text-align:center;padding:var(--space-lg);color:var(--text-muted);font-size:0.8125rem">
          <svg style="width:32px;height:32px;opacity:0.2;margin:0 auto var(--space-sm)"><use href="#icon-adaptation"/></svg>
          <div>No adaptations executed yet</div>
        </div>
      `;
      return;
    }

    const statusColors = { 'completed': 'var(--color-healthy)', 'failed': 'var(--color-critical)', 'executing': 'var(--color-warning)' };

    const rows = history.slice(-20).reverse().map(h => `
      <tr>
        <td><span class="abs-row-badge" style="border:1px solid ${statusColors[h.status] || 'var(--text-muted)'};color:${statusColors[h.status] || 'var(--text-muted)'};background:transparent;font-size:0.6rem">${h.status}</span></td>
        <td style="font-family:var(--font-mono);font-size:0.75rem">${h.strategy || '--'}</td>
        <td style="font-family:var(--font-mono)">${h.service || '--'}</td>
        <td style="font-family:var(--font-mono);font-size:0.75rem">${h.adaptation_id || '--'}</td>
        <td style="font-family:var(--font-mono);font-size:0.75rem">${h.started_at ? new Date(h.started_at * 1000).toLocaleTimeString() : '--'}</td>
      </tr>
    `).join('');

    container.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Status</th><th>Strategy</th><th>Service</th><th>ID</th><th>Time</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderAdpConfig(config) {
    const container = document.getElementById('adp-config-grid');
    if (!container || !config) return;

    const items = [
      { label: 'Latency Target', value: config.latency_target + 's', desc: '< 30 seconds' },
      { label: 'Scale Up CPU', value: config.scale_up_cpu + '%', desc: 'Auto-scale trigger' },
      { label: 'Scale Down CPU', value: config.scale_down_cpu + '%', desc: 'Scale-in threshold' },
      { label: 'Traffic Health', value: (config.traffic_shift_health * 100).toFixed(0) + '%', desc: 'Shift trigger' },
      { label: 'Flag EB Trigger', value: (config.feature_flag_eb_trigger * 100).toFixed(0) + '%', desc: 'Error budget %' },
      { label: 'Adaptation Window', value: formatDuration(config.adaptation_window), desc: 'Escalate to Recovery' },
    ];

    if (!adaptationInitialized) {
      container.innerHTML = items.map(item => `
        <div class="det-config-item">
          <div class="det-config-label">${item.label}</div>
          <div class="det-config-value">${item.value}</div>
          <div style="font-size:0.65rem;color:var(--text-muted);margin-top:2px">${item.desc}</div>
        </div>
      `).join('');
    }
  }

  window.refreshAdaptation = refreshAdaptation;

  // ---------------------------------------------------------------------------
  // Recovery Tab
  // ---------------------------------------------------------------------------
  let recoveryData = null;
  let recoveryInitialized = false;

  async function refreshRecovery() {
    const data = await fetchJSON('/api/aref/recovery');
    if (data && data.runbooks !== undefined) {
      recoveryData = data;
      renderRecovery();
    }
  }

  function renderRecovery() {
    if (!recoveryData) return;
    const d = recoveryData;

    const runbooks = d.runbooks || [];
    const execHistory = d.execution_history || [];
    const activeRecs = d.recoveries || [];

    updateRecCard('active', d.active_recoveries || 0,
      d.active_recoveries > 0 ? 'Incidents recovering' : 'No active recoveries');
    updateRecCard('total', d.total_recovered || 0,
      d.total_recovered > 0 ? 'Successfully resolved' : 'No incidents recovered');
    updateRecCard('runbooks', runbooks.length, `Across ${new Set(runbooks.map(r => r.tier)).size} tiers`);
    updateRecCard('executions', execHistory.length,
      execHistory.length > 0 ? `${execHistory.filter(e => e.steps_completed === e.total_steps).length} fully completed` : 'No runs yet');

    renderRecoveryTiers(d.tier_targets || {}, activeRecs);
    renderRunbookCatalog(runbooks);
    renderActiveRecoveries(activeRecs);
    renderExecHistory(execHistory);
    renderRecConfig(d.config);

    recoveryInitialized = true;
  }

  function updateRecCard(key, value, subtitle) {
    const valEl = document.querySelector(`[data-rec-value="${key}"]`);
    const subEl = document.querySelector(`[data-rec-sub="${key}"]`);
    if (valEl) valEl.textContent = value.toString();
    if (subEl) subEl.textContent = subtitle;
  }

  const TIER_COLORS = {
    'T0_EMERGENCY': '#ef4444',
    'T1_MINIMUM': '#f59e0b',
    'T2_FUNCTIONAL': '#3b82f6',
    'T3_FULL': '#10b981',
    'T4_HARDENING': '#8b5cf6',
  };

  function renderRecoveryTiers(tiers, activeRecs) {
    const container = document.getElementById('rec-tiers-container');
    if (!container) return;

    const entries = Object.entries(tiers);
    if (entries.length === 0) {
      container.innerHTML = '<div class="abs-empty">No tier definitions loaded</div>';
      return;
    }

    const activeTiers = new Set(activeRecs.map(r => r.current_tier));

    container.innerHTML = `<div class="rec-tier-track">
      ${entries.map(([tierKey, t]) => {
        const color = TIER_COLORS[tierKey] || 'var(--text-muted)';
        const active = activeTiers.has(tierKey);
        const tierNum = tierKey.charAt(1);
        return `
          <div class="rec-tier-node ${active ? 'rec-tier-node--active' : ''}">
            <div class="rec-tier-marker" style="background:${color};${active ? 'box-shadow:0 0 12px ' + color : ''}">T${tierNum}</div>
            <div class="rec-tier-info">
              <div class="rec-tier-label">${t.label}</div>
              <div class="rec-tier-range">${t.range}</div>
              <div class="rec-tier-target">Target: ${formatDuration(t.target_seconds)}</div>
            </div>
          </div>
        `;
      }).join('<div class="rec-tier-connector"></div>')}
    </div>`;
  }

  function renderRunbookCatalog(runbooks) {
    const container = document.getElementById('rec-runbooks-container');
    const countEl = document.querySelector('[data-rec-rb-count]');
    if (!container) return;

    if (countEl) countEl.textContent = `${runbooks.length} runbook${runbooks.length !== 1 ? 's' : ''}`;

    if (runbooks.length === 0) {
      container.innerHTML = '<div class="abs-empty">No runbooks defined</div>';
      return;
    }

    container.innerHTML = runbooks.map(rb => {
      const color = TIER_COLORS[rb.tier] || 'var(--text-muted)';
      const tierNum = rb.tier.charAt(1);
      const autoSteps = rb.steps.filter(s => s.automated).length;
      return `
        <div class="rec-runbook">
          <div class="rec-runbook-header">
            <div class="rec-tier-marker rec-tier-marker--sm" style="background:${color}">T${tierNum}</div>
            <div class="rec-runbook-name">${rb.name.replace(/_/g, ' ')}</div>
            <div class="abs-row-stat">v${rb.version}</div>
          </div>
          <div class="rec-runbook-desc">${rb.description}</div>
          <div class="rec-runbook-meta">
            <span>${rb.steps_count} steps</span>
            <span>${autoSteps} automated</span>
            <span>${rb.steps_count - autoSteps} manual</span>
            <span>svc: ${rb.service}</span>
          </div>
          <div class="rec-runbook-steps">
            ${rb.steps.map(s => `
              <div class="rec-step">
                <div class="rec-step-num">${s.order}</div>
                <div class="rec-step-body">
                  <div class="rec-step-action">${s.action.replace(/_/g, ' ')}</div>
                  <div class="rec-step-desc">${s.description}</div>
                </div>
                <div class="rec-step-tags">
                  <span class="rec-step-role">${s.role}</span>
                  ${s.automated ? '<span class="rec-step-auto">AUTO</span>' : ''}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }).join('');
  }

  function renderActiveRecoveries(recs) {
    const container = document.getElementById('rec-active-container');
    const countEl = document.querySelector('[data-rec-active-count]');
    if (!container) return;

    if (countEl) countEl.textContent = `${recs.length} active`;

    if (recs.length === 0) {
      container.innerHTML = `
        <div style="text-align:center;padding:var(--space-lg);color:var(--text-muted);font-size:0.8125rem">
          <svg style="width:32px;height:32px;opacity:0.2;margin:0 auto var(--space-sm)"><use href="#icon-healthy"/></svg>
          <div>No active recoveries</div>
          <div class="metrics-kpi-target" style="margin-top:var(--space-xs)">Recoveries trigger on emergency alerts or adaptation escalation</div>
        </div>
      `;
      return;
    }

    container.innerHTML = recs.map(r => {
      const color = TIER_COLORS[r.current_tier] || 'var(--text-muted)';
      const elapsed = r.elapsed || 0;
      return `
        <div class="abs-row">
          <div class="abs-row-state" style="background:${color};box-shadow:0 0 8px ${color}"></div>
          <div class="abs-row-name">${r.incident_id}</div>
          <div class="abs-row-badge" style="border:1px solid ${color};color:${color};background:transparent">${r.current_tier}</div>
          <div class="abs-row-stat">${formatDuration(elapsed)} elapsed</div>
        </div>
      `;
    }).join('');
  }

  function renderExecHistory(history) {
    const container = document.getElementById('rec-exec-table');
    if (!container) return;

    if (!history.length) {
      container.innerHTML = `
        <div style="text-align:center;padding:var(--space-lg);color:var(--text-muted);font-size:0.8125rem">
          <svg style="width:32px;height:32px;opacity:0.2;margin:0 auto var(--space-sm)"><use href="#icon-recovery"/></svg>
          <div>No runbook executions yet</div>
        </div>
      `;
      return;
    }

    const rows = history.slice(-15).reverse().map(h => {
      const color = TIER_COLORS[h.tier] || 'var(--text-muted)';
      const complete = h.steps_completed === h.total_steps;
      return `
        <tr>
          <td><span class="rec-tier-marker rec-tier-marker--sm" style="background:${color}">${h.tier ? h.tier.substring(0, 2) : '--'}</span></td>
          <td style="font-family:var(--font-mono);font-size:0.75rem">${h.runbook || '--'}</td>
          <td style="font-family:var(--font-mono);font-size:0.75rem">${h.incident_id || '--'}</td>
          <td><span style="color:${complete ? 'var(--color-healthy)' : 'var(--color-warning)'}">${h.steps_completed}/${h.total_steps}</span></td>
          <td style="font-family:var(--font-mono);font-size:0.75rem">${h.duration ? h.duration.toFixed(2) + 's' : '--'}</td>
          <td style="font-family:var(--font-mono);font-size:0.75rem">${h.summary || '--'}</td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Tier</th><th>Runbook</th><th>Incident</th><th>Steps</th><th>Duration</th><th>Summary</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderRecConfig(config) {
    const container = document.getElementById('rec-config-grid');
    if (!container || !config) return;

    const items = [
      { label: 'MTTR Target', value: formatDuration(config.mttr_target), desc: '< 15 minutes' },
      { label: 'T0 Target', value: formatDuration(config.t0_target), desc: 'Emergency stabilization' },
      { label: 'T1 Target', value: formatDuration(config.t1_target), desc: 'Minimum viable recovery' },
      { label: 'T2 Target', value: formatDuration(config.t2_target), desc: 'Functional recovery' },
      { label: 'T3 Target', value: formatDuration(config.t3_target), desc: 'Full restoration' },
      { label: 'T4 Target', value: config.t4_target_days + ' days', desc: 'Post-incident hardening' },
      { label: 'Drill Interval', value: config.drill_interval_days + ' days', desc: 'Quarterly runbook drills' },
    ];

    if (!recoveryInitialized) {
      container.innerHTML = items.map(item => `
        <div class="det-config-item">
          <div class="det-config-label">${item.label}</div>
          <div class="det-config-value">${item.value}</div>
          <div style="font-size:0.65rem;color:var(--text-muted);margin-top:2px">${item.desc}</div>
        </div>
      `).join('');
    }
  }

  window.refreshRecovery = refreshRecovery;

  // ---------------------------------------------------------------------------
  // Evolution (Pillar V)
  // ---------------------------------------------------------------------------
  let evolutionInitialized = false;

  async function refreshEvolution() {
    const data = await fetchJSON('/api/aref/evolution');
    if (data && data.total_reviews !== undefined) {
      renderEvoSummary(data);
      renderEvoReviewProcess(data.review_process || []);
      renderEvoVelocity(data.improvement_velocity || {}, data.action_tracker || {});
      renderEvoByPillar(data.action_tracker || {});
      renderEvoReviews(data.reviews || []);
      renderEvoPatterns(data.patterns || []);
      renderEvoActionsTable(data.action_items || []);
      renderEvoKnowledgeBase(data.knowledge_base_entries || []);
      renderEvoConfig(data.config || {});
      evolutionInitialized = true;
    }
  }

  function renderEvoSummary(d) {
    const tracker = d.action_tracker || {};
    const openCount = tracker.open || 0;
    const completedCount = tracker.completed || 0;

    setText('[data-evo-value="reviews"]', d.total_reviews);
    setText('[data-evo-sub="reviews"]', `${(d.reviews || []).length} with full detail`);

    setText('[data-evo-value="actions"]', tracker.total || 0);
    setText('[data-evo-sub="actions"]', `${openCount} open / ${completedCount} completed`);

    setText('[data-evo-value="patterns"]', (d.patterns || []).length);
    const rr = d.recurrence_rate || 0;
    const rrTarget = (d.config || {}).recurrence_rate_target || 10;
    setText('[data-evo-sub="patterns"]', `${rr.toFixed(1)}% recurrence (target <${rrTarget}%)`);

    setText('[data-evo-value="kb"]', d.knowledge_base_size || 0);
    setText('[data-evo-sub="kb"]', 'Stored incident entries');
  }

  function renderEvoReviewProcess(steps) {
    const el = document.getElementById('evo-review-process');
    if (!el || !steps.length) return;
    el.innerHTML = `<div class="evo-process-track">${steps.map((s, i) => `
      ${i > 0 ? '<div class="evo-process-connector"></div>' : ''}
      <div class="evo-process-node">
        <div class="evo-process-marker">${s.step}</div>
        <div class="evo-process-info">
          <div class="evo-process-name">${s.name}</div>
          <div class="evo-process-desc">${s.description}</div>
        </div>
      </div>
    `).join('')}</div>`;
  }

  function renderEvoVelocity(velocity, tracker) {
    const el = document.getElementById('evo-velocity');
    if (!el) return;
    const completed = velocity.actions_completed_this_quarter || 0;
    const target = velocity.target || 8;
    const pct = Math.min(100, (completed / target) * 100);
    const completionRate = velocity.completion_rate || 0;
    const targetRate = velocity.target_completion_rate || 85;
    const ratePct = Math.min(100, (completionRate / targetRate) * 100);
    const onTrack = velocity.on_track;

    el.innerHTML = `
      <div class="evo-velocity-grid">
        <div class="evo-velocity-metric">
          <div class="evo-velocity-label">Actions This Quarter</div>
          <div class="evo-velocity-row">
            <span class="evo-velocity-value">${completed}</span>
            <span class="evo-velocity-target">/ ${target} target</span>
            <span class="evo-velocity-badge ${onTrack ? 'evo-velocity-badge--ok' : 'evo-velocity-badge--warn'}">${onTrack ? 'ON TRACK' : 'BEHIND'}</span>
          </div>
          <div class="evo-bar-track">
            <div class="evo-bar-fill ${pct >= 100 ? 'evo-bar-fill--ok' : 'evo-bar-fill--partial'}" style="width:${pct}%"></div>
          </div>
        </div>
        <div class="evo-velocity-metric">
          <div class="evo-velocity-label">Completion Rate</div>
          <div class="evo-velocity-row">
            <span class="evo-velocity-value">${completionRate.toFixed(1)}%</span>
            <span class="evo-velocity-target">/ ${targetRate}% target</span>
            <span class="evo-velocity-badge ${completionRate >= targetRate ? 'evo-velocity-badge--ok' : 'evo-velocity-badge--warn'}">${completionRate >= targetRate ? 'MET' : 'BELOW'}</span>
          </div>
          <div class="evo-bar-track">
            <div class="evo-bar-fill ${ratePct >= 100 ? 'evo-bar-fill--ok' : 'evo-bar-fill--partial'}" style="width:${ratePct}%"></div>
          </div>
        </div>
        <div class="evo-velocity-metric">
          <div class="evo-velocity-label">Overdue Items</div>
          <div class="evo-velocity-row">
            <span class="evo-velocity-value">${tracker.overdue || 0}</span>
            <span class="evo-velocity-target">of ${tracker.total || 0} total</span>
          </div>
        </div>
      </div>
    `;
  }

  function renderEvoByPillar(tracker) {
    const el = document.getElementById('evo-by-pillar');
    if (!el) return;
    const byPillar = tracker.by_pillar || {};
    const pillars = ['detection', 'absorption', 'adaptation', 'recovery', 'evolution'];
    const colors = {
      detection: 'var(--color-detection)',
      absorption: 'var(--color-absorption)',
      adaptation: 'var(--color-adaptation)',
      recovery: 'var(--color-recovery)',
      evolution: 'var(--color-evolution)',
    };
    const maxCount = Math.max(1, ...Object.values(byPillar));

    el.innerHTML = pillars.map(p => {
      const count = byPillar[p] || 0;
      const pct = (count / maxCount) * 100;
      return `
        <div class="evo-pillar-row">
          <span class="evo-pillar-name">${p.charAt(0).toUpperCase() + p.slice(1)}</span>
          <div class="evo-pillar-bar-track">
            <div class="evo-pillar-bar-fill" style="width:${pct}%;background:${colors[p]}"></div>
          </div>
          <span class="evo-pillar-count">${count}</span>
        </div>
      `;
    }).join('');
  }

  function renderEvoReviews(reviews) {
    const el = document.getElementById('evo-reviews-list');
    if (!el) return;
    if (!reviews.length) {
      el.innerHTML = '<div class="abs-empty">No reviews yet</div>';
      return;
    }
    el.innerHTML = reviews.slice().reverse().map(r => {
      const sevClass = r.severity === 'sev1' ? 'evo-sev--critical' : r.severity === 'sev2' ? 'evo-sev--warning' : 'evo-sev--info';
      const factors = (r.contributing_factors || []);
      const effectiveness = r.response_effectiveness || {};
      return `
        <div class="evo-review">
          <div class="evo-review-header">
            <span class="evo-review-id">${r.incident_id}</span>
            <span class="evo-sev-badge ${sevClass}">${(r.severity || '').toUpperCase()}</span>
          </div>
          <div class="evo-review-summary">${r.summary || ''}</div>
          <div class="evo-review-metrics">
            <span class="evo-review-metric">MTTD: ${r.mttd || 0}s</span>
            <span class="evo-review-metric">Recovery: ${r.recovery_duration || 0}s</span>
            <span class="evo-review-metric">Adapt Lag: ${(r.adaptation_latency || 0).toFixed(0)}s</span>
            <span class="evo-review-metric">Containment: ${r.blast_radius_containment || 0}%</span>
          </div>
          <div class="evo-review-effectiveness">
            ${Object.entries(effectiveness).map(([k, v]) => `
              <span class="evo-eff-tag ${v === 'effective' ? 'evo-eff--ok' : 'evo-eff--warn'}">${k}: ${v === 'effective' ? 'OK' : 'IMPROVE'}</span>
            `).join('')}
          </div>
          ${factors.length ? `<div class="evo-review-factors">${factors.map(f => `
            <div class="evo-factor"><span class="evo-factor-cat">${f.category}</span> ${f.factor}</div>
          `).join('')}</div>` : ''}
          ${(r.lessons_learned || []).length ? `<div class="evo-review-lessons">${r.lessons_learned.map(l => `
            <div class="evo-lesson">${l}</div>
          `).join('')}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  function renderEvoPatterns(patterns) {
    const el = document.getElementById('evo-patterns-list');
    if (!el) return;
    if (!patterns.length) {
      el.innerHTML = '<div class="abs-empty">No patterns registered</div>';
      return;
    }
    el.innerHTML = patterns.map(p => {
      const matchCount = p._match_count || 0;
      return `
        <div class="evo-pattern">
          <div class="evo-pattern-header">
            <span class="evo-pattern-svc">${p.service}</span>
            <span class="evo-sev-badge ${p.severity === 'sev1' ? 'evo-sev--critical' : p.severity === 'sev2' ? 'evo-sev--warning' : 'evo-sev--info'}">${(p.severity || '').toUpperCase()}</span>
            ${matchCount > 0 ? `<span class="evo-match-badge">${matchCount} match${matchCount > 1 ? 'es' : ''}</span>` : ''}
          </div>
          <div class="evo-pattern-meta">
            <span>Detection: ${p.detection_class || 'unknown'}</span>
            <span>From: ${p.created_from || 'N/A'}</span>
          </div>
          <div class="evo-pattern-factors">
            ${(p.contributing_factors || []).map(f => `<span class="evo-factor-tag">${f}</span>`).join('')}
          </div>
          ${(p.affected_services || []).length ? `<div class="evo-pattern-affected">Affected: ${p.affected_services.join(', ')}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  function renderEvoActionsTable(items) {
    const el = document.getElementById('evo-actions-table');
    if (!el) return;
    if (!items.length) {
      el.innerHTML = '<div class="abs-empty">No action items</div>';
      return;
    }
    const rows = items.slice().sort((a, b) => {
      const pOrd = {high: 0, medium: 1, low: 2};
      return (pOrd[a.priority] || 2) - (pOrd[b.priority] || 2);
    });
    el.innerHTML = `
      <table class="det-alert-table">
        <thead><tr>
          <th>ID</th><th>Title</th><th>Pillar</th><th>Priority</th><th>Status</th><th>Incident</th>
        </tr></thead>
        <tbody>${rows.map(a => {
          const statusCls = a.status === 'completed' ? 'evo-status--done' : a.is_overdue ? 'evo-status--overdue' : 'evo-status--open';
          const statusLabel = a.is_overdue ? 'OVERDUE' : a.status.toUpperCase();
          return `<tr>
            <td><code class="evo-action-id">${a.action_id}</code></td>
            <td>${a.title}</td>
            <td><span class="evo-pillar-tag evo-pillar-tag--${a.pillar}">${a.pillar}</span></td>
            <td><span class="evo-priority-tag evo-priority--${a.priority}">${a.priority.toUpperCase()}</span></td>
            <td><span class="evo-status-tag ${statusCls}">${statusLabel}</span></td>
            <td><code>${a.incident_id}</code></td>
          </tr>`;
        }).join('')}</tbody>
      </table>
    `;
  }

  function renderEvoKnowledgeBase(entries) {
    const el = document.getElementById('evo-kb-list');
    if (!el) return;
    if (!entries.length) {
      el.innerHTML = '<div class="abs-empty">Knowledge base empty</div>';
      return;
    }
    el.innerHTML = entries.map(e => {
      return `
        <div class="evo-kb-entry">
          <div class="evo-kb-header">
            <span class="evo-kb-id">${e.incident_id}</span>
            <span class="evo-sev-badge ${e.severity === 'sev1' ? 'evo-sev--critical' : e.severity === 'sev2' ? 'evo-sev--warning' : 'evo-sev--info'}">${(e.severity || '').toUpperCase()}</span>
            <span class="evo-kb-svc">${e.service}</span>
          </div>
          <div class="evo-kb-metrics">
            <span>MTTD: ${e.mttd || 'N/A'}s</span>
            <span>MTTR: ${e.mttr || 'N/A'}s</span>
            <span>Class: ${e.detection_class || 'unknown'}</span>
          </div>
          ${(e.lessons_learned || []).length ? `<div class="evo-kb-lessons">${e.lessons_learned.map(l => `<div class="evo-lesson">${l}</div>`).join('')}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  function renderEvoConfig(cfg) {
    const el = document.getElementById('evo-config-grid');
    if (!el || !cfg) return;
    const items = [
      ['Velocity Target', `>${cfg.improvement_velocity_target || 8} actions/quarter`],
      ['Completion Rate Target', `>${cfg.action_completion_rate_target || 85}%`],
      ['Recurrence Rate Target', `<${cfg.recurrence_rate_target || 10}%`],
      ['Knowledge Share Window', `${cfg.knowledge_share_target_hours || 72}h`],
      ['Review Deadline', `${cfg.review_deadline_hours || 72}h post-incident`],
    ];
    el.innerHTML = items.map(([k, v]) => `
      <div class="det-config-item"><span class="det-config-label">${k}</span><span class="det-config-value">${v}</span></div>
    `).join('');
  }

  window.refreshEvolution = refreshEvolution;

  // ---------------------------------------------------------------------------
  // Services Tab
  // ---------------------------------------------------------------------------

  async function refreshServicesTab() {
    const data = await fetchJSON('/api/aref/services');
    if (!data || !data.services) return;

    renderSvcSummary(data);
    renderSvcDepMap(data.dependency_graph || {}, data.services, data.circuit_breakers_by_service || {});
    renderSvcDetailCards(data);
    renderSvcInfra(data.infrastructure || {}, data.dependency_graph || {});
    renderSvcRateLimiters(data.rate_limiters || {});
  }

  function renderSvcSummary(d) {
    const svcs = Object.entries(d.services || {});
    const healthy = svcs.filter(([, s]) => s.status === 'healthy').length;
    const cbsByService = d.circuit_breakers_by_service || {};
    const totalCbs = Object.values(cbsByService).reduce((acc, arr) => acc + arr.length, 0);
    const instances = d.instances || {};
    const totalInstances = Object.values(instances).reduce((a, b) => a + b, 0);

    setText('[data-svc-value="total"]', svcs.length);
    setText('[data-svc-sub="total"]', `${svcs.length} registered microservices`);

    setText('[data-svc-value="healthy"]', healthy);
    setText('[data-svc-sub="healthy"]', `${healthy}/${svcs.length} passing health checks`);

    setText('[data-svc-value="breakers"]', totalCbs);
    const openCbs = Object.values(cbsByService).flat().filter(cb => cb.state === 'open').length;
    setText('[data-svc-sub="breakers"]', openCbs > 0 ? `${openCbs} OPEN` : 'All closed');

    setText('[data-svc-value="instances"]', totalInstances);
    setText('[data-svc-sub="instances"]', `Across ${svcs.length} services`);
  }

  function renderSvcDepMap(graph, services, cbsByService) {
    const el = document.getElementById('svc-dep-map');
    if (!el) return;

    // Build layers: tier 0 = no dependents among services, tier 1 = depends on tier 0, etc.
    const serviceNames = Object.keys(services);
    const infraNames = Object.keys(graph).filter(n => !serviceNames.includes(n));

    // Simple layout: gateway -> mid-tier -> data stores
    const layers = {
      'Entry': serviceNames.filter(n => (graph[n]?.dependents || []).length === 0),
      'Application': serviceNames.filter(n => {
        const deps = graph[n]?.dependents || [];
        const hasDeps = deps.length > 0;
        const hasSvcDeps = (graph[n]?.dependencies || []).some(d => serviceNames.includes(d));
        return hasDeps && hasSvcDeps;
      }),
      'Service': serviceNames.filter(n => {
        const deps = graph[n]?.dependents || [];
        const hasDeps = deps.length > 0;
        const onlyInfraDeps = (graph[n]?.dependencies || []).every(d => !serviceNames.includes(d) || infraNames.includes(d));
        return hasDeps && onlyInfraDeps;
      }),
      'Infrastructure': infraNames,
    };

    // Deduplicate — a service should appear in only one layer (earliest)
    const placed = new Set();
    for (const [, members] of Object.entries(layers)) {
      for (let i = members.length - 1; i >= 0; i--) {
        if (placed.has(members[i])) {
          members.splice(i, 1);
        } else {
          placed.add(members[i]);
        }
      }
    }
    // Ensure every service is in at least one layer
    serviceNames.forEach(s => {
      if (!placed.has(s)) {
        layers['Application'].push(s);
        placed.add(s);
      }
    });

    const nodeStatus = (name) => {
      const svc = services[name];
      if (svc) return svc.status === 'healthy' ? 'healthy' : 'unhealthy';
      return 'infra';
    };

    const nodeType = (name) => graph[name]?.type || 'service';
    const nodeCriticality = (name) => graph[name]?.criticality || 'high';

    el.innerHTML = `
      <div class="svc-dep-layers">
        ${Object.entries(layers).filter(([, m]) => m.length > 0).map(([layerName, members]) => `
          <div class="svc-dep-layer">
            <div class="svc-dep-layer-label">${layerName}</div>
            <div class="svc-dep-layer-nodes">
              ${members.map(name => {
                const cbs = cbsByService[name] || [];
                const openCount = cbs.filter(c => c.state === 'open').length;
                const deps = (graph[name]?.dependencies || []);
                return `
                  <div class="svc-dep-node svc-dep-node--${nodeStatus(name)}" data-node="${name}">
                    <div class="svc-dep-node-name">${name}</div>
                    <div class="svc-dep-node-type">${nodeType(name)} / ${nodeCriticality(name)}</div>
                    ${cbs.length ? `<div class="svc-dep-node-cbs">${cbs.length} CB${openCount > 0 ? ` (${openCount} open)` : ''}</div>` : ''}
                    ${deps.length ? `<div class="svc-dep-node-deps">${deps.map(d => `<span class="svc-dep-arrow">${d}</span>`).join('')}</div>` : ''}
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        `).join('<div class="svc-dep-layer-connector"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg></div>')}
      </div>
    `;
  }

  function renderSvcDetailCards(data) {
    const el = document.getElementById('svc-detail-cards');
    if (!el) return;
    const services = data.services || {};
    const cbsByService = data.circuit_breakers_by_service || {};
    const degradation = data.degradation || {};
    const instances = data.instances || {};
    const graph = data.dependency_graph || {};

    el.innerHTML = `<div class="card-grid card-grid--2col">
      ${Object.entries(services).map(([name, svc]) => {
        const cbs = cbsByService[name] || [];
        const deg = degradation[name];
        const inst = instances[name] || 1;
        const deps = graph[name]?.dependencies || [];
        const dependents = graph[name]?.dependents || [];
        const failureModes = graph[name]?.failure_modes || [];
        const healthy = svc.status === 'healthy';

        return `
          <div class="card svc-detail-card">
            <div class="card-header">
              <div style="display:flex;align-items:center;gap:var(--space-sm)">
                <span class="svc-status-dot svc-status-dot--${healthy ? 'ok' : 'down'}"></span>
                <div class="card-title">${name}</div>
              </div>
              <span class="svc-version-badge">v${svc.version || '?'}</span>
            </div>
            <div class="svc-detail-desc">${svc.description || ''}</div>
            <div class="svc-detail-meta">
              <span class="svc-detail-chip">Port: ${svc.port || '?'}</span>
              <span class="svc-detail-chip">Instances: ${inst}</span>
              ${deg ? `<span class="svc-detail-chip svc-deg-chip--${deg.current_level}">${deg.current_level.toUpperCase()}</span>` : ''}
            </div>

            ${cbs.length ? `
            <div class="svc-detail-section">
              <div class="svc-detail-section-title">Circuit Breakers</div>
              ${cbs.map(cb => `
                <div class="svc-cb-row">
                  <span class="svc-cb-name">${cb.dependency}</span>
                  <span class="svc-cb-state svc-cb-state--${cb.state}">${cb.state.toUpperCase()}</span>
                  <span class="svc-cb-stats">${cb.failure_count}F / ${cb.success_count}S</span>
                </div>
              `).join('')}
            </div>` : ''}

            <div class="svc-detail-section">
              <div class="svc-detail-section-title">Dependencies</div>
              <div class="svc-dep-tags">
                ${deps.length ? deps.map(d => `<span class="svc-dep-tag">${d}</span>`).join('') : '<span class="svc-dep-tag svc-dep-tag--none">None</span>'}
              </div>
            </div>

            ${dependents.length ? `
            <div class="svc-detail-section">
              <div class="svc-detail-section-title">Depended on by</div>
              <div class="svc-dep-tags">
                ${dependents.map(d => `<span class="svc-dep-tag svc-dep-tag--rev">${d}</span>`).join('')}
              </div>
            </div>` : ''}

            ${failureModes.length ? `
            <div class="svc-detail-section">
              <div class="svc-detail-section-title">Failure Modes</div>
              <div class="svc-dep-tags">
                ${failureModes.map(f => `<span class="svc-dep-tag svc-dep-tag--fail">${f}</span>`).join('')}
              </div>
            </div>` : ''}
          </div>
        `;
      }).join('')}
    </div>`;
  }

  function renderSvcInfra(infra, graph) {
    const el = document.getElementById('svc-infra');
    if (!el) return;
    const entries = Object.entries(infra).filter(([, v]) => Object.keys(v).length > 0);
    if (!entries.length) {
      el.innerHTML = '<div class="abs-empty">No infrastructure dependencies registered</div>';
      return;
    }
    el.innerHTML = `<div class="svc-infra-grid">${entries.map(([name, info]) => {
      const node = graph[name] || {};
      return `
        <div class="svc-infra-node">
          <div class="svc-infra-header">
            <span class="svc-infra-name">${name}</span>
            <span class="svc-infra-type">${info.type || node.type || 'infra'}</span>
          </div>
          <div class="svc-infra-meta">
            <span>Criticality: ${info.criticality || node.criticality || 'high'}</span>
          </div>
          <div class="svc-detail-section-title" style="margin-top:var(--space-sm)">Used by</div>
          <div class="svc-dep-tags">
            ${(info.dependents || node.dependents || []).map(d => `<span class="svc-dep-tag">${d}</span>`).join('')}
          </div>
          ${(info.failure_modes || node.failure_modes || []).length ? `
          <div class="svc-detail-section-title" style="margin-top:var(--space-sm)">Failure Modes</div>
          <div class="svc-dep-tags">
            ${(info.failure_modes || node.failure_modes || []).map(f => `<span class="svc-dep-tag svc-dep-tag--fail">${f}</span>`).join('')}
          </div>` : ''}
        </div>
      `;
    }).join('')}</div>`;
  }

  function renderSvcRateLimiters(limiters) {
    const el = document.getElementById('svc-rate-limiters');
    if (!el) return;
    const entries = Object.entries(limiters);
    if (!entries.length) {
      el.innerHTML = '<div class="abs-empty">No rate limiters registered</div>';
      return;
    }
    el.innerHTML = entries.map(([name, rl]) => {
      const pct = (rl.tokens / rl.capacity) * 100;
      return `
        <div class="svc-rl-row">
          <span class="svc-rl-name">${name}</span>
          <div class="svc-rl-bar-track">
            <div class="svc-rl-bar-fill ${pct < 20 ? 'svc-rl-bar--low' : pct < 50 ? 'svc-rl-bar--mid' : 'svc-rl-bar--ok'}" style="width:${pct}%"></div>
          </div>
          <span class="svc-rl-stat">${rl.tokens}/${rl.capacity} tokens</span>
          <span class="svc-rl-rate">${rl.rate}/s</span>
        </div>
      `;
    }).join('');
  }

  window.refreshServicesTab = refreshServicesTab;

  // ---------------------------------------------------------------------------
  // Timeline Tab
  // ---------------------------------------------------------------------------
  let _tlActiveFilter = 'all';

  const CATEGORY_COLORS = {
    detection: 'var(--color-detection)',
    absorption: 'var(--color-absorption)',
    adaptation: 'var(--color-adaptation)',
    recovery: 'var(--color-recovery)',
    evolution: 'var(--color-evolution)',
    chaos: 'var(--color-chaos)',
    system: 'var(--text-muted)',
  };

  const SEVERITY_COLORS = {
    info: 'var(--color-detection)',
    warning: 'var(--color-warning)',
    critical: 'var(--color-critical)',
    emergency: 'var(--color-critical)',
  };

  async function refreshTimelineTab() {
    const data = await fetchJSON('/api/aref/timeline');
    if (!data || !data.events) return;

    const summary = data.summary || {};
    renderTlSummary(summary);
    renderTlByCategory(summary.by_category || {});
    renderTlBySeverity(summary.by_severity || {});
    renderTlFilterBar(summary.by_category || {});
    renderTlEventFeed(data.events || []);
  }

  function renderTlSummary(summary) {
    const total = summary.total || 0;
    const cats = Object.keys(summary.by_category || {}).length;
    const sources = Object.keys(summary.by_source || {}).length;
    const sevs = summary.by_severity || {};
    const warnPlus = (sevs.warning || 0) + (sevs.critical || 0) + (sevs.emergency || 0);

    setText('[data-tl-value="total"]', total);
    setText('[data-tl-total]', `${total} events`);
    setText('[data-tl-value="categories"]', cats);
    setText('[data-tl-sub="categories"]', Object.keys(summary.by_category || {}).join(', ') || 'None');
    setText('[data-tl-value="sources"]', sources);
    setText('[data-tl-sub="sources"]', Object.keys(summary.by_source || {}).join(', ').substring(0, 50) || 'None');
    setText('[data-tl-value="warnings"]', warnPlus);
    setText('[data-tl-sub="warnings"]', `${sevs.warning || 0}W / ${sevs.critical || 0}C / ${sevs.emergency || 0}E`);
  }

  function renderTlByCategory(cats) {
    const el = document.getElementById('tl-by-category');
    if (!el) return;
    const entries = Object.entries(cats).sort((a, b) => b[1] - a[1]);
    const maxCount = Math.max(1, ...entries.map(e => e[1]));
    el.innerHTML = entries.map(([cat, count]) => {
      const pct = (count / maxCount) * 100;
      const color = CATEGORY_COLORS[cat] || 'var(--text-muted)';
      return `
        <div class="tl-bar-row">
          <span class="tl-bar-label">${cat}</span>
          <div class="tl-bar-track">
            <div class="tl-bar-fill" style="width:${pct}%;background:${color}"></div>
          </div>
          <span class="tl-bar-count">${count}</span>
        </div>
      `;
    }).join('');
  }

  function renderTlBySeverity(sevs) {
    const el = document.getElementById('tl-by-severity');
    if (!el) return;
    const order = ['info', 'warning', 'critical', 'emergency'];
    const entries = order.filter(s => sevs[s]).map(s => [s, sevs[s]]);
    const maxCount = Math.max(1, ...entries.map(e => e[1]));
    el.innerHTML = entries.map(([sev, count]) => {
      const pct = (count / maxCount) * 100;
      const color = SEVERITY_COLORS[sev] || 'var(--text-muted)';
      return `
        <div class="tl-bar-row">
          <span class="tl-bar-label">${sev.toUpperCase()}</span>
          <div class="tl-bar-track">
            <div class="tl-bar-fill" style="width:${pct}%;background:${color}"></div>
          </div>
          <span class="tl-bar-count">${count}</span>
        </div>
      `;
    }).join('');
  }

  function renderTlFilterBar(cats) {
    const el = document.getElementById('tl-filter-bar');
    if (!el) return;
    const allCats = ['all', ...Object.keys(cats)];
    el.innerHTML = allCats.map(cat => `
      <button class="tl-filter-btn ${_tlActiveFilter === cat ? 'tl-filter-btn--active' : ''}"
              onclick="setTlFilter('${cat}')">${cat === 'all' ? 'All' : cat}</button>
    `).join('');
  }

  window.setTlFilter = function(cat) {
    _tlActiveFilter = cat;
    refreshTimelineTab();
  };

  function renderTlEventFeed(events) {
    const el = document.getElementById('tl-event-feed');
    if (!el) return;

    let filtered = events;
    if (_tlActiveFilter !== 'all') {
      filtered = events.filter(e => e.category === _tlActiveFilter);
    }

    const sorted = filtered.slice().sort((a, b) => b.timestamp - a.timestamp);

    if (!sorted.length) {
      el.innerHTML = '<div class="abs-empty">No events match the current filter</div>';
      return;
    }

    el.innerHTML = `
      <div class="tl-feed">
        ${sorted.map(e => {
          const cat = e.category || 'system';
          const sev = e.severity || 'info';
          const ts = new Date(e.timestamp * 1000);
          const timeStr = ts.toLocaleTimeString();
          const dateStr = ts.toLocaleDateString();
          const color = CATEGORY_COLORS[cat] || 'var(--text-muted)';
          const payload = e.payload || {};
          const payloadKeys = Object.keys(payload);
          const payloadPreview = payloadKeys.slice(0, 4).map(k => {
            const v = payload[k];
            const val = typeof v === 'object' ? JSON.stringify(v).substring(0, 30) : String(v).substring(0, 30);
            return `<span class="tl-payload-kv"><span class="tl-payload-key">${k}:</span> ${val}</span>`;
          }).join('');

          return `
            <div class="tl-event">
              <div class="tl-event-dot" style="background:${color}"></div>
              <div class="tl-event-body">
                <div class="tl-event-header">
                  <span class="tl-event-type">${e.event_type}</span>
                  <span class="tl-cat-badge" style="background:${color}20;color:${color}">${cat}</span>
                  <span class="tl-sev-badge tl-sev-badge--${sev}">${sev.toUpperCase()}</span>
                  ${e.correlation_id ? `<span class="tl-corr-id">${e.correlation_id}</span>` : ''}
                </div>
                <div class="tl-event-meta">
                  <span class="tl-event-source">${e.source || 'unknown'}</span>
                  <span class="tl-event-time">${timeStr} &middot; ${dateStr}</span>
                  <span class="tl-event-id">${e.event_id || ''}</span>
                </div>
                ${payloadPreview ? `<div class="tl-event-payload">${payloadPreview}</div>` : ''}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  window.refreshTimelineTab = refreshTimelineTab;

  // ---------------------------------------------------------------------------
  // Main Render
  // ---------------------------------------------------------------------------
  function render() {
    renderCRSGauge(state.crs);
    renderRadar(state.pillars);
    renderPillarCards();
    renderServices();
    renderAlerts();
    renderTimeline();

    // Update header status smoothly
    const headerStatus = document.getElementById('system-status');
    if (headerStatus) {
      const hasActive = state.alerts.some(a => a.severity === 'critical' || a.severity === 'emergency');
      let newClass, newText;
      if (state.chaosActive) {
        newClass = 'header-badge badge-critical';
        newText = 'CHAOS ACTIVE';
      } else if (hasActive) {
        newClass = 'header-badge badge-critical';
        newText = 'INCIDENT';
      } else {
        newClass = 'header-badge badge-healthy';
        newText = 'OPERATIONAL';
      }
      if (headerStatus.textContent !== newText) {
        headerStatus.style.transition = 'opacity 0.2s ease';
        headerStatus.style.opacity = '0';
        setTimeout(() => {
          headerStatus.className = newClass;
          headerStatus.textContent = newText;
          headerStatus.style.opacity = '1';
        }, 200);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Chaos Controls
  // ---------------------------------------------------------------------------
  window.startChaosExperiment = async function (experiment) {
    await postJSON('/api/aref/chaos/start', { experiment });
    await refreshData();
  };

  window.stopAllChaos = async function () {
    await postJSON('/api/aref/chaos/stop');
    await refreshData();
  };

  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------
  window.navigate = function (section) {
    document.querySelectorAll('.sidebar-nav-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.page-section').forEach(el => el.style.display = 'none');

    const navItem = document.querySelector(`[data-section="${section}"]`);
    const sectionEl = document.getElementById(`section-${section}`);

    if (navItem) navItem.classList.add('active');
    if (sectionEl) sectionEl.style.display = 'block';

    // Load section data on navigation
    if (section === 'metrics') refreshMetrics();
    if (section === 'detection') refreshDetection();
    if (section === 'absorption') refreshAbsorption();
    if (section === 'adaptation') refreshAdaptation();
    if (section === 'recovery') refreshRecovery();
    if (section === 'evolution') refreshEvolution();
    if (section === 'services') refreshServicesTab();
    if (section === 'timeline') refreshTimelineTab();
  };

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', async () => {
    await refreshData();
    setInterval(refreshData, POLL_INTERVAL);
  });

})();
