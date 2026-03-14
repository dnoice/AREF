/*
* ============================================================================
* AREF Widget Manager — Drag, Resize, Toggle, Theme, Layout Persistence
*
* Title: AREF Widget Manager (AREF Edition - v3.0)
* File Name: widgets.js
* Relative Path: aref/dashboard/static/js/widgets.js
* Version: 3.0.0
* Date: 2026-03-13
* Author: Dennis 'dnoice' Smaltz
* A.I. Acknowledgement: Anthropic - Claude Opus 4
* Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
*
* Features:
*   - Theme switching (light/dark) with localStorage persistence
*   - Widget collapse/expand with smooth animation
*   - Widget visibility toggle with customizer panel
*   - Drag-and-drop reordering within widget grids
*   - Layout persistence to localStorage
*   - Respects prefers-color-scheme on first visit
* ============================================================================
*/

(function () {
  'use strict';

  const STORAGE_KEY_THEME  = 'aref-theme';
  const STORAGE_KEY_LAYOUT = 'aref-widget-layout';

  // =========================================================================
  // Theme Manager
  // =========================================================================
  const ThemeManager = {
    init() {
      const saved = localStorage.getItem(STORAGE_KEY_THEME);
      if (saved) {
        this.apply(saved);
      } else {
        // Respect system preference
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.apply(prefersDark ? 'dark' : 'dark'); // default dark
      }

      // Watch for system theme changes
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem(STORAGE_KEY_THEME)) {
          this.apply(e.matches ? 'dark' : 'light');
        }
      });
    },

    apply(theme) {
      document.documentElement.setAttribute('data-theme', theme);
      this._updateToggleIcon(theme);
    },

    toggle() {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      this.apply(next);
      localStorage.setItem(STORAGE_KEY_THEME, next);
    },

    _updateToggleIcon(theme) {
      const btn = document.getElementById('theme-toggle-btn');
      if (!btn) return;
      btn.textContent = theme === 'dark' ? '\u2600' : '\u263E';  // sun / moon
      btn.setAttribute('title', `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`);
    },
  };

  // =========================================================================
  // Widget Manager
  // =========================================================================
  const WidgetManager = {
    _widgets: new Map(),  // id -> { el, collapsed, hidden }
    _dragState: null,

    init() {
      // Discover all widgets
      document.querySelectorAll('.widget[data-widget-id]').forEach(el => {
        const id = el.dataset.widgetId;
        this._widgets.set(id, {
          el,
          collapsed: false,
          hidden: false,
          title: el.dataset.widgetTitle || id,
        });
      });

      // Inject headers into widgets that need them
      this._widgets.forEach((w, id) => {
        if (!w.el.querySelector('.widget-header')) {
          this._injectHeader(w.el, id, w.title);
        }
      });

      // Restore saved layout
      this._restoreLayout();

      // Bind collapse/close buttons
      this._bindControls();

      // Init drag and drop
      this._initDragDrop();

      // Build customizer panel content
      this._buildCustomizer();
    },

    _injectHeader(el, id, title) {
      const body = el.innerHTML;
      el.innerHTML = `
        <div class="widget-header">
          <span class="widget-drag-handle" title="Drag to reorder">\u22EE\u22EE</span>
          <span class="widget-title">${title}</span>
          <div class="widget-controls">
            <button class="widget-btn collapse-btn" title="Collapse">\u25BE</button>
            <button class="widget-btn close-btn" title="Hide widget">\u00D7</button>
          </div>
        </div>
        <div class="widget-body">${body}</div>
      `;
    },

    _bindControls() {
      document.addEventListener('click', (e) => {
        // Collapse button
        const collapseBtn = e.target.closest('.widget-btn.collapse-btn');
        if (collapseBtn) {
          const widget = collapseBtn.closest('.widget[data-widget-id]');
          if (widget) this.toggleCollapse(widget.dataset.widgetId);
          return;
        }

        // Close button
        const closeBtn = e.target.closest('.widget-btn.close-btn');
        if (closeBtn) {
          const widget = closeBtn.closest('.widget[data-widget-id]');
          if (widget) this.toggleVisibility(widget.dataset.widgetId, false);
          return;
        }
      });
    },

    toggleCollapse(id) {
      const w = this._widgets.get(id);
      if (!w) return;
      w.collapsed = !w.collapsed;
      w.el.classList.toggle('is-collapsed', w.collapsed);
      const btn = w.el.querySelector('.collapse-btn');
      if (btn) btn.classList.toggle('is-collapsed', w.collapsed);
      this._saveLayout();
    },

    toggleVisibility(id, visible) {
      const w = this._widgets.get(id);
      if (!w) return;
      w.hidden = !visible;
      w.el.classList.toggle('is-hidden', w.hidden);
      // Update customizer checkbox
      const checkbox = document.querySelector(`.customizer-checkbox[data-widget-id="${id}"]`);
      if (checkbox) checkbox.checked = visible;
      this._saveLayout();
    },

    showAll() {
      this._widgets.forEach((w, id) => {
        this.toggleVisibility(id, true);
        if (w.collapsed) this.toggleCollapse(id);
      });
    },

    // -----------------------------------------------------------------------
    // Drag and Drop
    // -----------------------------------------------------------------------
    _initDragDrop() {
      document.addEventListener('pointerdown', (e) => {
        const handle = e.target.closest('.widget-drag-handle');
        if (!handle) return;

        const widget = handle.closest('.widget[data-widget-id]');
        if (!widget) return;

        e.preventDefault();
        const grid = widget.parentElement;
        if (!grid) return;

        const rect = widget.getBoundingClientRect();
        this._dragState = {
          widget,
          grid,
          startX: e.clientX,
          startY: e.clientY,
          offsetX: e.clientX - rect.left,
          offsetY: e.clientY - rect.top,
          placeholder: null,
        };

        widget.classList.add('is-dragging');
        widget.style.position = 'fixed';
        widget.style.left = rect.left + 'px';
        widget.style.top = rect.top + 'px';
        widget.style.width = rect.width + 'px';
        widget.style.zIndex = '1000';

        // Create placeholder
        const placeholder = document.createElement('div');
        placeholder.className = 'widget is-drag-over';
        placeholder.style.minHeight = rect.height + 'px';
        placeholder.style.opacity = '0.3';
        grid.insertBefore(placeholder, widget);
        this._dragState.placeholder = placeholder;

        const onMove = (me) => {
          if (!this._dragState) return;
          widget.style.left = (me.clientX - this._dragState.offsetX) + 'px';
          widget.style.top = (me.clientY - this._dragState.offsetY) + 'px';

          // Find closest sibling to insert before
          const siblings = [...grid.querySelectorAll('.widget[data-widget-id]:not(.is-dragging)')];
          let closest = null;
          let closestDist = Infinity;
          for (const sib of siblings) {
            const sibRect = sib.getBoundingClientRect();
            const dist = Math.abs(me.clientY - (sibRect.top + sibRect.height / 2));
            if (dist < closestDist) {
              closestDist = dist;
              closest = sib;
            }
          }

          if (closest && closest !== placeholder) {
            const closestRect = closest.getBoundingClientRect();
            if (me.clientY < closestRect.top + closestRect.height / 2) {
              grid.insertBefore(placeholder, closest);
            } else {
              grid.insertBefore(placeholder, closest.nextSibling);
            }
          }
        };

        const onUp = () => {
          if (!this._dragState) return;
          widget.classList.remove('is-dragging');
          widget.style.position = '';
          widget.style.left = '';
          widget.style.top = '';
          widget.style.width = '';
          widget.style.zIndex = '';

          // Insert widget at placeholder position
          if (this._dragState.placeholder && this._dragState.placeholder.parentElement) {
            grid.insertBefore(widget, this._dragState.placeholder);
            this._dragState.placeholder.remove();
          }

          this._dragState = null;
          this._saveLayout();

          document.removeEventListener('pointermove', onMove);
          document.removeEventListener('pointerup', onUp);
        };

        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
      });
    },

    // -----------------------------------------------------------------------
    // Customizer Panel
    // -----------------------------------------------------------------------
    _buildCustomizer() {
      const panel = document.getElementById('customizer-panel');
      if (!panel) return;

      const container = panel.querySelector('.customizer-widgets-list');
      if (!container) return;

      // Group widgets by their section
      const sections = new Map();
      this._widgets.forEach((w, id) => {
        const section = w.el.closest('.page-section');
        const sectionName = section ? (section.id.replace('section-', '') || 'overview') : 'other';
        if (!sections.has(sectionName)) sections.set(sectionName, []);
        sections.get(sectionName).push({ id, title: w.title, hidden: w.hidden });
      });

      let html = '';
      sections.forEach((widgets, section) => {
        const label = section.charAt(0).toUpperCase() + section.slice(1);
        html += `<div class="customizer-section">
          <div class="customizer-section-title">${label}</div>`;
        widgets.forEach(w => {
          html += `
          <div class="customizer-item">
            <span class="customizer-item-label">${w.title}</span>
            <label class="toggle-switch">
              <input type="checkbox" class="customizer-checkbox"
                     data-widget-id="${w.id}" ${w.hidden ? '' : 'checked'}>
              <span class="toggle-slider"></span>
            </label>
          </div>`;
        });
        html += '</div>';
      });

      container.innerHTML = html;

      // Bind toggle events
      container.addEventListener('change', (e) => {
        const cb = e.target.closest('.customizer-checkbox');
        if (cb) {
          this.toggleVisibility(cb.dataset.widgetId, cb.checked);
        }
      });

      // Reset button
      const resetBtn = panel.querySelector('.customizer-reset');
      if (resetBtn) {
        resetBtn.addEventListener('click', () => {
          this.showAll();
          localStorage.removeItem(STORAGE_KEY_LAYOUT);
          this._buildCustomizer();
        });
      }
    },

    toggleCustomizer() {
      const panel = document.getElementById('customizer-panel');
      const btn = document.getElementById('customizer-toggle-btn');
      if (panel) {
        panel.classList.toggle('is-open');
        if (btn) btn.classList.toggle('active');
      }
    },

    // -----------------------------------------------------------------------
    // Layout Persistence
    // -----------------------------------------------------------------------
    _saveLayout() {
      const layout = {};
      this._widgets.forEach((w, id) => {
        const parent = w.el.parentElement;
        const order = parent ? [...parent.children].indexOf(w.el) : 0;
        layout[id] = { collapsed: w.collapsed, hidden: w.hidden, order };
      });
      localStorage.setItem(STORAGE_KEY_LAYOUT, JSON.stringify(layout));
    },

    _restoreLayout() {
      const saved = localStorage.getItem(STORAGE_KEY_LAYOUT);
      if (!saved) return;

      try {
        const layout = JSON.parse(saved);

        // Restore collapsed/hidden states
        Object.entries(layout).forEach(([id, state]) => {
          const w = this._widgets.get(id);
          if (!w) return;

          if (state.collapsed) {
            w.collapsed = true;
            w.el.classList.add('is-collapsed');
            const btn = w.el.querySelector('.collapse-btn');
            if (btn) btn.classList.add('is-collapsed');
          }

          if (state.hidden) {
            w.hidden = true;
            w.el.classList.add('is-hidden');
          }
        });

        // Restore order within each grid container
        const grids = new Map();
        this._widgets.forEach((w, id) => {
          const parent = w.el.parentElement;
          if (!parent) return;
          if (!grids.has(parent)) grids.set(parent, []);
          grids.get(parent).push({ id, el: w.el, order: layout[id]?.order ?? 999 });
        });

        grids.forEach((items, parent) => {
          items.sort((a, b) => a.order - b.order);
          items.forEach(item => parent.appendChild(item.el));
        });
      } catch (e) {
        console.warn('Failed to restore widget layout:', e);
      }
    },
  };

  // =========================================================================
  // Initialization
  // =========================================================================
  function init() {
    ThemeManager.init();
    WidgetManager.init();

    // Bind theme toggle
    const themeBtn = document.getElementById('theme-toggle-btn');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => ThemeManager.toggle());
    }

    // Bind customizer toggle
    const custBtn = document.getElementById('customizer-toggle-btn');
    if (custBtn) {
      custBtn.addEventListener('click', () => WidgetManager.toggleCustomizer());
    }
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose for external use
  window.AREFWidgets = WidgetManager;
  window.AREFTheme = ThemeManager;

})();
