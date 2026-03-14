/*
* ============================================================================
* ✒ Metadata
*     - Title: AREF Dashboard Widget Manager (AREF Edition - v1.0)
*     - File Name: widgets.js
*     - Relative Path: aref/dashboard/static/js/widgets.js
*     - Artifact Type: script
*     - Version: 1.0.0
*     - Date: 2026-03-14
*     - Update: Friday, March 14, 2026
*     - Author: Dennis 'dnoice' Smaltz
*     - A.I. Acknowledgement: Anthropic - Claude Opus 4
*     - Signature: ︻デ═─── ✦ ✦ ✦ | Aim Twice, Shoot Once!
*
* ✒ Description:
*     Widget management system for the AREF Dashboard. Provides dual-theme
*     switching (dark/light), drag-and-drop widget reordering, per-widget
*     collapse/expand and visibility toggling, a slide-in customizer panel,
*     and full localStorage persistence of all user preferences.
*
* ✒ Key Features:
*     - Feature 1: Theme management — reads/writes localStorage 'aref-theme',
*                   applies data-theme attribute to <html>, updates toggle icon
*     - Feature 2: Widget registry — keyed by data-widget-id, stores visible,
*                   collapsed, and order state; initialized from localStorage
*     - Feature 3: Drag-and-drop reordering — native HTML5 drag events on
*                   .widget-wrapper[draggable] elements; persists new order
*     - Feature 4: Collapse/expand — toggles .widget-collapsed class, persists
*     - Feature 5: Visibility toggle — shows/hides widget wrappers, persists
*     - Feature 6: Customizer panel — slide-in panel listing all widgets with
*                   visibility toggles and collapse buttons
*     - Feature 7: Automatic DOM scan on DOMContentLoaded; wires all controls
*
* ✒ Usage Instructions:
*     Loaded by index.html before dashboard.js:
*         <script src="/static/js/widgets.js"></script>
*
*     Widget HTML structure:
*         <div class="widget-wrapper" data-widget-id="my-widget" draggable="true">
*           <div class="widget-header"> ... </div>
*           <div class="widget-body"> ... </div>
*         </div>
*
*     WidgetManager is exposed globally:
*         WidgetManager.toggleCollapse('my-widget')
*         WidgetManager.toggleVisibility('my-widget')
*
* ✒ Other Important Information:
*     - Storage keys: 'aref-theme' (string), 'aref-widgets' (JSON)
*     - No external dependencies; pure vanilla JS
*     - Compatible platforms: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
* ----------------------------------------------------------------------------
 */

(function () {
  'use strict';

  /* ------------------------------------------------------------------ */
  /* Default widget definitions (order determines initial DOM order)     */
  /* ------------------------------------------------------------------ */
  const DEFAULT_WIDGETS = [
    { id: 'pillar-cards',   title: 'Pillar Overview', visible: true, collapsed: false, order: 0 },
    { id: 'crs-gauge',      title: 'CRS Score',       visible: true, collapsed: false, order: 1 },
    { id: 'maturity-radar', title: 'Maturity Radar',  visible: true, collapsed: false, order: 2 },
  ];

  /* ------------------------------------------------------------------ */
  /* WidgetManager                                                        */
  /* ------------------------------------------------------------------ */
  const WidgetManager = {
    /** @type {Map<string, {id:string,title:string,visible:boolean,collapsed:boolean,order:number}>} */
    widgets: new Map(),

    /* ---- Theme ---- */

    initTheme() {
      const saved = localStorage.getItem('aref-theme') || 'dark';
      document.documentElement.setAttribute('data-theme', saved);
      this._updateThemeToggleIcon(saved);
    },

    toggleTheme() {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('aref-theme', next);
      this._updateThemeToggleIcon(next);
    },

    _updateThemeToggleIcon(theme) {
      const btn = document.getElementById('theme-toggle');
      if (!btn) return;
      const icon = btn.querySelector('.theme-icon');
      if (icon) icon.textContent = theme === 'dark' ? '☀' : '🌙';
      btn.setAttribute('title', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
      btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    },

    /* ---- Widget Registry ---- */

    _loadState() {
      try {
        const raw = localStorage.getItem('aref-widgets');
        if (raw) {
          const saved = JSON.parse(raw);
          if (Array.isArray(saved)) {
            saved.forEach(w => {
              if (w && w.id) this.widgets.set(w.id, w);
            });
            return;
          }
        }
      } catch (err) { /* ignore corrupt data */ }
      /* Fall back to defaults */
      DEFAULT_WIDGETS.forEach(w => this.widgets.set(w.id, { ...w }));
    },

    saveState() {
      const arr = Array.from(this.widgets.values());
      localStorage.setItem('aref-widgets', JSON.stringify(arr));
    },

    /* ---- Apply saved state to DOM ---- */

    _applyStates() {
      this.widgets.forEach((state, id) => {
        const el = document.querySelector(`.widget-wrapper[data-widget-id="${id}"]`);
        if (!el) return;

        if (!state.visible) {
          el.style.display = 'none';
        } else {
          el.style.display = '';
        }

        if (state.collapsed) {
          el.classList.add('widget-collapsed');
        } else {
          el.classList.remove('widget-collapsed');
        }
      });
    },

    /* ---- Collapse / Expand ---- */

    toggleCollapse(id) {
      const el = document.querySelector(`.widget-wrapper[data-widget-id="${id}"]`);
      if (!el) return;

      const state = this.widgets.get(id);
      const nowCollapsed = !el.classList.contains('widget-collapsed');

      el.classList.toggle('widget-collapsed', nowCollapsed);

      if (state) {
        state.collapsed = nowCollapsed;
      } else {
        this.widgets.set(id, { id, title: id, visible: true, collapsed: nowCollapsed, order: 999 });
      }

      this.saveState();
      this.renderCustomizer();
    },

    /* ---- Visibility Toggle ---- */

    toggleVisibility(id) {
      const el = document.querySelector(`.widget-wrapper[data-widget-id="${id}"]`);
      const state = this.widgets.get(id);
      const currentlyVisible = el ? el.style.display !== 'none' : (state ? state.visible : true);
      const nextVisible = !currentlyVisible;

      if (el) el.style.display = nextVisible ? '' : 'none';

      if (state) {
        state.visible = nextVisible;
      } else {
        this.widgets.set(id, { id, title: id, visible: nextVisible, collapsed: false, order: 999 });
      }

      this.saveState();
      this.renderCustomizer();
    },

    /* ---- Drag and Drop ---- */

    initDragAndDrop() {
      const wrappers = () => Array.from(document.querySelectorAll('.widget-wrapper[draggable="true"]'));
      let dragSrc = null;

      document.addEventListener('dragstart', (e) => {
        const wrapper = e.target.closest('.widget-wrapper[draggable="true"]');
        if (!wrapper) return;
        dragSrc = wrapper;
        document.body.classList.add('dragging-widget');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', wrapper.dataset.widgetId || '');
        setTimeout(() => wrapper.style.opacity = '0.4', 0);
      });

      document.addEventListener('dragover', (e) => {
        const wrapper = e.target.closest('.widget-wrapper[draggable="true"]');
        if (!wrapper || wrapper === dragSrc) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        /* Highlight drop target */
        wrappers().forEach(w => w.classList.remove('drag-over'));
        wrapper.classList.add('drag-over');
      });

      document.addEventListener('dragleave', (e) => {
        const wrapper = e.target.closest('.widget-wrapper[draggable="true"]');
        if (wrapper) wrapper.classList.remove('drag-over');
      });

      document.addEventListener('drop', (e) => {
        const target = e.target.closest('.widget-wrapper[draggable="true"]');
        if (!target || !dragSrc || target === dragSrc) return;
        e.preventDefault();
        target.classList.remove('drag-over');

        const parent = target.parentNode;
        if (!parent) return;

        const allWidgets = wrappers().filter(w => w.parentNode === parent);
        const srcIdx  = allWidgets.indexOf(dragSrc);
        const tgtIdx  = allWidgets.indexOf(target);

        if (srcIdx < tgtIdx) {
          parent.insertBefore(dragSrc, target.nextSibling);
        } else {
          parent.insertBefore(dragSrc, target);
        }

        /* Update order state */
        Array.from(parent.querySelectorAll('.widget-wrapper[data-widget-id]')).forEach((el, i) => {
          const id = el.dataset.widgetId;
          const s = this.widgets.get(id);
          if (s) s.order = i;
        });
        this.saveState();
      });

      document.addEventListener('dragend', (e) => {
        document.body.classList.remove('dragging-widget');
        wrappers().forEach(w => {
          w.style.opacity = '';
          w.classList.remove('drag-over');
        });
        dragSrc = null;
      });
    },

    /* ---- Customizer Panel ---- */

    openCustomizer() {
      const panel = document.getElementById('widget-customizer');
      if (panel) panel.removeAttribute('hidden');
      this.renderCustomizer();
    },

    closeCustomizer() {
      const panel = document.getElementById('widget-customizer');
      if (panel) panel.setAttribute('hidden', '');
    },

    renderCustomizer() {
      const list = document.getElementById('customizer-list');
      if (!list) return;

      list.innerHTML = '';

      /* Merge DOM widgets not yet in registry */
      document.querySelectorAll('.widget-wrapper[data-widget-id]').forEach((el, i) => {
        const id = el.dataset.widgetId;
        if (!this.widgets.has(id)) {
          const titleEl = el.querySelector('.widget-title');
          this.widgets.set(id, {
            id,
            title: titleEl ? titleEl.textContent.trim() : id,
            visible: el.style.display !== 'none',
            collapsed: el.classList.contains('widget-collapsed'),
            order: i,
          });
        }
      });

      const sorted = Array.from(this.widgets.values()).sort((a, b) => a.order - b.order);

      sorted.forEach(state => {
        const item = document.createElement('div');
        item.className = 'customizer-item';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'customizer-item-title';
        titleSpan.textContent = state.title;

        const actions = document.createElement('div');
        actions.className = 'customizer-item-actions';

        /* Visibility toggle switch */
        const label = document.createElement('label');
        label.className = 'toggle-switch';
        label.title = 'Toggle visibility';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = state.visible;
        checkbox.addEventListener('change', () => this.toggleVisibility(state.id));
        const track = document.createElement('span');
        track.className = 'toggle-track';
        label.appendChild(checkbox);
        label.appendChild(track);

        /* Collapse button */
        const collapseBtn = document.createElement('button');
        collapseBtn.className = 'icon-btn widget-collapse-btn';
        collapseBtn.title = state.collapsed ? 'Expand' : 'Collapse';
        collapseBtn.textContent = state.collapsed ? '+' : '−';
        collapseBtn.addEventListener('click', () => this.toggleCollapse(state.id));

        actions.appendChild(label);
        actions.appendChild(collapseBtn);
        item.appendChild(titleSpan);
        item.appendChild(actions);
        list.appendChild(item);
      });
    },

    /* ---- Scan DOM for widget wrappers ---- */

    _scanWidgets() {
      document.querySelectorAll('.widget-wrapper[data-widget-id]').forEach((el, i) => {
        const id = el.dataset.widgetId;
        if (!this.widgets.has(id)) {
          const titleEl = el.querySelector('.widget-title');
          this.widgets.set(id, {
            id,
            title: titleEl ? titleEl.textContent.trim() : id,
            visible: true,
            collapsed: false,
            order: i,
          });
        }
      });
    },

    /* ---- Init ---- */

    init() {
      this._loadState();
      this.initTheme();
      this._scanWidgets();
      this._applyStates();
      this.initDragAndDrop();

      const themeToggle = document.getElementById('theme-toggle');
      if (themeToggle) {
        themeToggle.addEventListener('click', () => this.toggleTheme());
      }

      const openBtn = document.getElementById('open-customizer');
      if (openBtn) {
        openBtn.addEventListener('click', () => this.openCustomizer());
      }

      const closeBtn = document.getElementById('close-customizer');
      if (closeBtn) {
        closeBtn.addEventListener('click', () => this.closeCustomizer());
      }

      /* Close overlay when clicking the backdrop */
      const overlay = document.getElementById('widget-customizer');
      if (overlay) {
        overlay.addEventListener('click', (e) => {
          if (e.target === overlay) this.closeCustomizer();
        });
      }
    },
  };

  /* ------------------------------------------------------------------ */
  /* Bootstrap on DOMContentLoaded                                        */
  /* ------------------------------------------------------------------ */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => WidgetManager.init());
  } else {
    WidgetManager.init();
  }

  /* Expose globally */
  window.WidgetManager = WidgetManager;

}());
