/**
 * SciFi Research Cockpit - Interactive Frontend Application
 * Pure JavaScript (ES6+), zero-build SPA.
 */

(() => {
  'use strict';

  // ---------------------------------------------------------------------------
  // Global State
  // ---------------------------------------------------------------------------
  const state = {
    projects: [],
    currentProjectId: null,
    papers: [],
    graphData: { nodes: [], edges: [] },
    reprints: [],
    selectedPaper: null,
    network: null,
    physicsEnabled: true,
    activeTab: 'network', // 'network' | 'papers' | 'reprints'
    searchQuery: '',
    oaFilter: 'ALL',
    sortField: 'citations',
    reprintStatusFilter: 'ALL',
  };

  // Color mapping matching OA standards
  const OA_COLORS = {
    gold: { bg: '#eab308', text: '#ffffff' },
    green: { bg: '#22c55e', text: '#ffffff' },
    hybrid: { bg: '#3b82f6', text: '#ffffff' },
    bronze: { bg: '#f97316', text: '#ffffff' },
    diamond: { bg: '#06b6d4', text: '#ffffff' },
    closed: { bg: '#64748b', text: '#ffffff' },
    retracted: { bg: '#ef4444', text: '#ffffff' },
  };

  // ---------------------------------------------------------------------------
  // DOM Elements
  // ---------------------------------------------------------------------------
  const elements = {
    projectsDropdown: document.getElementById('projects-dropdown'),
    sessionSelector: document.getElementById('session-selector'),
    syncStatusText: document.getElementById('sync-status-text'),
    btnRefresh: document.getElementById('btn-refresh'),

    // Tabs
    tabBtnNetwork: document.getElementById('tab-btn-network'),
    tabBtnPapers: document.getElementById('tab-btn-papers'),
    tabBtnReprints: document.getElementById('tab-btn-reprints'),
    tabMetaText: document.getElementById('tab-meta-text'),

    // Views
    viewNetwork: document.getElementById('view-network'),
    viewPapers: document.getElementById('view-papers'),
    viewReprints: document.getElementById('view-reprints'),

    // Network Canvas & Controls
    networkContainer: document.getElementById('network-container'),
    btnZoomIn: document.getElementById('btn-zoom-in'),
    btnZoomOut: document.getElementById('btn-zoom-out'),
    btnZoomFit: document.getElementById('btn-zoom-fit'),
    btnTogglePhysics: document.getElementById('btn-toggle-physics'),
    physicsIndicator: document.getElementById('physics-indicator'),

    // Badges & Metrics
    badgeNodesCount: document.getElementById('badge-nodes-count'),
    badgePapersCount: document.getElementById('badge-papers-count'),
    badgeReprintsCount: document.getElementById('badge-reprints-count'),
    statTotalPapers: document.getElementById('stat-total-papers'),
    statOaRate: document.getElementById('stat-oa-rate'),
    statPaywalled: document.getElementById('stat-paywalled'),
    statInfluential: document.getElementById('stat-influential'),

    // Papers View
    papersSearchInput: document.getElementById('papers-search-input'),
    papersFilterOa: document.getElementById('papers-filter-oa'),
    papersSort: document.getElementById('papers-sort'),
    papersTableBody: document.getElementById('papers-table-body'),

    // Reprints View
    reprintsFilterStatus: document.getElementById('reprints-filter-status'),
    reprintsTable: document.getElementById('reprints-table'),
    reprintsTableBody: document.getElementById('reprints-table-body'),

    // Drawer
    paperDrawer: document.getElementById('paper-drawer'),
    drawerBackdrop: document.getElementById('drawer-backdrop'),
    drawerCloseBtn: document.getElementById('drawer-close-btn'),
    drawerTitle: document.getElementById('drawer-title'),
    drawerVenueYear: document.getElementById('drawer-venue-year'),
    drawerOaBadge: document.getElementById('drawer-oa-badge'),
    drawerRetractedBadge: document.getElementById('drawer-retracted-badge'),
    drawerDoi: document.getElementById('drawer-doi'),
    drawerCitations: document.getElementById('drawer-citations'),
    drawerGaps: document.getElementById('drawer-gaps'),
    drawerLocalPdf: document.getElementById('drawer-local-pdf'),
    drawerAuthorsList: document.getElementById('drawer-authors-list'),
    drawerAbstract: document.getElementById('drawer-abstract'),
    drawerBtnViewPdf: document.getElementById('drawer-btn-view-pdf'),
    drawerBtnIngestPdf: document.getElementById('drawer-btn-ingest-pdf'),

    // Modal
    ingestModal: document.getElementById('ingest-modal'),
    modalCloseBtn: document.getElementById('modal-close-btn'),
    modalCancelBtn: document.getElementById('modal-cancel-btn'),
    modalSubmitBtn: document.getElementById('modal-submit-btn'),
    modalPaperId: document.getElementById('modal-paper-id'),
    modalPdfPath: document.getElementById('modal-pdf-path'),

    // Toast
    toastContainer: document.getElementById('toast-container'),
  };

  // ---------------------------------------------------------------------------
  // Notification Toast Helper
  // ---------------------------------------------------------------------------
  function showToast(message, type = 'info') {
    if (!elements.toastContainer) return;
    const toast = document.createElement('div');
    const bgClass =
      type === 'success'
        ? 'bg-emerald-950 border-emerald-500/50 text-emerald-200'
        : type === 'error'
        ? 'bg-red-950 border-red-500/50 text-red-200'
        : 'bg-slate-900 border-slate-700 text-slate-200';

    toast.className = `toast border ${bgClass}`;
    toast.innerHTML = `
      <span>${escapeHtml(message)}</span>
      <button class="ml-3 text-slate-400 hover:text-white">&times;</button>
    `;

    const closeBtn = toast.querySelector('button');
    closeBtn.addEventListener('click', () => toast.remove());

    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 4000);
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ---------------------------------------------------------------------------
  // API Calls
  // ---------------------------------------------------------------------------
  async function fetchProjects() {
    try {
      elements.syncStatusText.textContent = 'Syncing...';
      const resp = await fetch('/api/projects');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.projects = data.projects || [];

      renderProjectsDropdown();

      if (state.projects.length > 0) {
        const activeId = state.currentProjectId || state.projects[0].id;
        await selectProject(activeId);
      } else {
        elements.projectsDropdown.innerHTML = '<option value="">No projects registered</option>';
        elements.syncStatusText.textContent = 'Store Empty (0 Projects)';
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
      elements.syncStatusText.textContent = 'Sync Error';
      showToast(`Error connecting to REST API: ${err.message}`, 'error');
    }
  }

  async function selectProject(projectId) {
    state.currentProjectId = projectId;
    elements.projectsDropdown.value = projectId;

    const proj = state.projects.find((p) => p.id === projectId);
    if (proj) {
      elements.syncStatusText.textContent = `Active: ${proj.name}`;
    }

    await loadProjectData(projectId);
  }

  async function loadProjectData(projectId) {
    try {
      const sessionId = elements.sessionSelector.value || '';
      const graphParam = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';

      // Fetch papers, graph, and reprints concurrently
      const [papersResp, graphResp, reprintsResp] = await Promise.all([
        fetch(`/api/projects/${projectId}/papers`),
        fetch(`/api/projects/${projectId}/graph${graphParam}`),
        fetch(`/api/reprints?project_id=${encodeURIComponent(projectId)}`),
      ]);

      if (papersResp.ok) {
        const pdata = await papersResp.json();
        state.papers = pdata.papers || [];
      } else {
        state.papers = [];
      }

      if (graphResp.ok) {
        const gdata = await graphResp.json();
        state.graphData = {
          nodes: gdata.nodes || [],
          edges: gdata.edges || [],
        };
      } else {
        state.graphData = { nodes: [], edges: [] };
      }

      if (reprintsResp.ok) {
        const rdata = await reprintsResp.json();
        state.reprints = rdata.reprints || [];
      } else {
        state.reprints = [];
      }

      updateMetrics();
      renderVisNetwork();
      renderPapersTable();
      renderReprintsTable();
    } catch (err) {
      console.error('Error loading project data:', err);
      showToast(`Failed to load project data: ${err.message}`, 'error');
    }
  }

  async function updateReprintEmail(reprintId, newEmail) {
    try {
      const resp = await fetch(`/api/reprints/${reprintId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author_email: newEmail.trim() }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      const updated = data.reprint;

      // Update state
      const idx = state.reprints.findIndex((r) => r.id === reprintId);
      if (idx !== -1) {
        state.reprints[idx] = updated;
      }

      showToast('Author email & mailto link updated!', 'success');
      renderReprintsTable();
    } catch (err) {
      console.error('Failed to update email:', err);
      showToast(`Error updating email: ${err.message}`, 'error');
    }
  }

  async function updateReprintStatus(reprintId, newStatus) {
    try {
      const resp = await fetch(`/api/reprints/${reprintId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      const updated = data.reprint;

      const idx = state.reprints.findIndex((r) => r.id === reprintId);
      if (idx !== -1) {
        state.reprints[idx] = updated;
      }

      showToast(`Reprint status set to ${newStatus}`, 'success');
      renderReprintsTable();
    } catch (err) {
      console.error('Failed to update status:', err);
      showToast(`Error updating status: ${err.message}`, 'error');
    }
  }

  async function submitIngestPdf(paperId, pdfPath) {
    try {
      const resp = await fetch('/api/papers/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: state.currentProjectId,
          paper_id: paperId,
          pdf_path: pdfPath.trim(),
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || `HTTP ${resp.status}`);
      }

      const res = await resp.json();
      const sizeStr = res.file_size ? ` (${(res.file_size / 1024).toFixed(1)} KB)` : '';
      showToast(`PDF ingested successfully!${sizeStr}`, 'success');
      closeIngestModal();

      // Refresh project data
      await loadProjectData(state.currentProjectId);

      // If drawer is open on this paper, update it
      if (state.selectedPaper && state.selectedPaper.id === paperId) {
        const updated = state.papers.find((p) => p.id === paperId);
        if (updated) openDrawer(updated);
      }
    } catch (err) {
      console.error('Ingest failed:', err);
      showToast(`PDF Ingest Error: ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------
  function renderProjectsDropdown() {
    elements.projectsDropdown.innerHTML = '';
    state.projects.forEach((proj) => {
      const opt = document.createElement('option');
      opt.value = proj.id;
      opt.textContent = `${proj.name} (${proj.paper_count} papers)`;
      elements.projectsDropdown.appendChild(opt);
    });
  }

  function updateMetrics() {
    const total = state.papers.length;
    const oaCount = state.papers.filter((p) => p.is_oa).length;
    const paywalledCount = total - oaCount;
    const influentialCount = state.papers.reduce((acc, p) => acc + (p.influential_citation_count || 0), 0);
    const oaRate = total > 0 ? Math.round((oaCount / total) * 100) : 0;

    elements.statTotalPapers.textContent = total;
    elements.statOaRate.textContent = `${oaRate}%`;
    elements.statPaywalled.textContent = paywalledCount;
    elements.statInfluential.textContent = influentialCount;

    elements.badgeNodesCount.textContent = state.graphData.nodes.length;
    elements.badgePapersCount.textContent = total;
    elements.badgeReprintsCount.textContent = state.reprints.length;

    elements.tabMetaText.textContent = `${total} papers • ${state.graphData.edges.length} citations`;
  }

  // ---------------------------------------------------------------------------
  // Vis.js Interactive DAG Lineage
  // ---------------------------------------------------------------------------
  function renderVisNetwork() {
    if (typeof vis === 'undefined' || !vis.Network) {
      elements.networkContainer.innerHTML =
        '<div class="p-8 text-center text-slate-400">Vis.js library is not available. Please verify internet connection.</div>';
      return;
    }

    const container = elements.networkContainer;
    const data = {
      nodes: new vis.DataSet(state.graphData.nodes),
      edges: new vis.DataSet(state.graphData.edges),
    };

    const options = {
      nodes: {
        shape: 'box',
        margin: 10,
        font: {
          face: 'ui-sans-serif, system-ui, sans-serif',
          size: 12,
          color: '#ffffff',
        },
        borderWidth: 1.5,
        shadow: {
          enabled: true,
          color: 'rgba(0, 0, 0, 0.4)',
          size: 6,
          x: 2,
          y: 2,
        },
      },
      edges: {
        smooth: {
          type: 'cubicBezier',
          forceDirection: 'horizontal',
          roundness: 0.4,
        },
        arrows: {
          to: { enabled: true, scaleFactor: 0.8 },
        },
      },
      layout: {
        improvedLayout: true,
      },
      physics: {
        enabled: state.physicsEnabled,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -40,
          centralGravity: 0.01,
          springLength: 120,
          springConstant: 0.08,
          damping: 0.4,
        },
        stabilization: {
          enabled: true,
          iterations: 150,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 150,
        selectable: true,
        multiselect: false,
        zoomView: true,
        dragView: true,
      },
    };

    if (state.network) {
      state.network.destroy();
    }

    state.network = new vis.Network(container, data, options);

    // Event handlers
    state.network.on('click', (params) => {
      if (params.nodes && params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const paper = state.papers.find((p) => p.id === nodeId);
        if (paper) {
          openDrawer(paper);
        } else {
          // Fallback paper minimal object from node
          const nodeObj = state.graphData.nodes.find((n) => n.id === nodeId);
          if (nodeObj) {
            openDrawer({
              id: nodeObj.id,
              title: nodeObj.title || nodeObj.label,
              year: nodeObj.year,
              is_oa: nodeObj.is_oa,
              oa_status: nodeObj.oa_status,
              citation_count: nodeObj.citation_count,
              influential_citation_count: nodeObj.influential_citation_count,
              is_retracted: nodeObj.is_retracted,
              abstract: 'Full abstract available in catalog.',
              authors: [],
            });
          }
        }
      }
    });

    // Double click to focus
    state.network.on('doubleClick', (params) => {
      if (params.nodes && params.nodes.length > 0) {
        state.network.focus(params.nodes[0], {
          scale: 1.4,
          animation: { duration: 400, easingFunction: 'easeInOutQuad' },
        });
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Papers Catalog Table View
  // ---------------------------------------------------------------------------
  function renderPapersTable() {
    let filtered = [...state.papers];

    // Filter by search
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      filtered = filtered.filter((p) => {
        const titleMatch = (p.title || '').toLowerCase().includes(q);
        const doiMatch = (p.doi || p.id || '').toLowerCase().includes(q);
        const venueMatch = (p.venue_name || '').toLowerCase().includes(q);
        const authorMatch = (p.authors || []).some((a) =>
          (a.name || '').toLowerCase().includes(q)
        );
        return titleMatch || doiMatch || venueMatch || authorMatch;
      });
    }

    // Filter by OA
    if (state.oaFilter === 'OA') {
      filtered = filtered.filter((p) => p.is_oa);
    } else if (state.oaFilter === 'CLOSED') {
      filtered = filtered.filter((p) => !p.is_oa);
    }

    // Sort
    if (state.sortField === 'citations') {
      filtered.sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0));
    } else if (state.sortField === 'year') {
      filtered.sort((a, b) => (b.year || 0) - (a.year || 0));
    } else if (state.sortField === 'title') {
      filtered.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    }

    elements.papersTableBody.innerHTML = '';

    if (filtered.length === 0) {
      elements.papersTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="py-8 text-center text-slate-500">
            No papers match current search criteria.
          </td>
        </tr>
      `;
      return;
    }

    filtered.forEach((paper) => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-800/40 transition cursor-pointer';

      // Authors summary
      const authorsStr =
        paper.authors && paper.authors.length > 0
          ? paper.authors.map((a) => a.name).slice(0, 3).join(', ') +
            (paper.authors.length > 3 ? ' et al.' : '')
          : 'Unknown Authors';

      // OA badge style
      const oaType = (paper.oa_status || 'closed').toLowerCase();
      const oaBadgeColor =
        oaType === 'gold'
          ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
          : oaType === 'green'
          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
          : oaType === 'hybrid'
          ? 'bg-blue-500/20 text-blue-300 border-blue-500/30'
          : oaType === 'bronze'
          ? 'bg-orange-500/20 text-orange-300 border-orange-500/30'
          : oaType === 'diamond'
          ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30'
          : 'bg-slate-700/50 text-slate-400 border-slate-600/50';

      // PDF status
      let pdfBadge = '<span class="text-slate-500">None</span>';
      if (paper.has_pdf && paper.local_pdf_path) {
        pdfBadge = '<span class="bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-2 py-0.5 rounded text-[10px] font-mono">Local PDF</span>';
      } else if (paper.pdf_url) {
        pdfBadge = '<span class="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded text-[10px] font-mono">Web PDF</span>';
      }

      tr.innerHTML = `
        <td class="py-3 px-4">
          <div class="font-semibold text-slate-200 hover:text-indigo-400 transition">${escapeHtml(paper.title)}</div>
          <div class="text-[11px] text-slate-400 mt-0.5">${escapeHtml(authorsStr)}</div>
        </td>
        <td class="py-3 px-3 text-slate-300">${paper.year || 'n.d.'}</td>
        <td class="py-3 px-4">
          <div class="text-slate-300 truncate max-w-[170px]" title="${escapeHtml(paper.venue_name || '')}">${escapeHtml(paper.venue_name || '-')}</div>
          ${paper.venue_tier ? `<span class="inline-block mt-0.5 text-[9px] uppercase font-bold px-1.5 py-0.2 bg-indigo-900/60 text-indigo-300 border border-indigo-700 rounded">${escapeHtml(paper.venue_tier)}</span>` : ''}
        </td>
        <td class="py-3 px-3">
          <div class="font-medium text-slate-200">${paper.citation_count || 0}</div>
          ${paper.influential_citation_count ? `<div class="text-[10px] text-indigo-400">${paper.influential_citation_count} influential</div>` : ''}
        </td>
        <td class="py-3 px-3">
          <span class="inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${oaBadgeColor}">
            ${escapeHtml(paper.oa_status || 'closed')}
          </span>
        </td>
        <td class="py-3 px-3">${pdfBadge}</td>
        <td class="py-3 px-4 text-right space-x-1.5" onclick="event.stopPropagation()">
          <button class="btn-inspect px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded border border-slate-700 text-[11px] transition">
            Details
          </button>
          <button class="btn-ingest px-2.5 py-1 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded text-[11px] transition">
            Ingest
          </button>
        </td>
      `;

      tr.addEventListener('click', () => openDrawer(paper));
      tr.querySelector('.btn-inspect').addEventListener('click', () => openDrawer(paper));
      tr.querySelector('.btn-ingest').addEventListener('click', () => openIngestModal(paper.id));

      elements.papersTableBody.appendChild(tr);
    });
  }

  // ---------------------------------------------------------------------------
  // Author Reprints Hub View
  // ---------------------------------------------------------------------------
  function renderReprintsTable() {
    let filtered = [...state.reprints];

    if (state.reprintStatusFilter !== 'ALL') {
      filtered = filtered.filter((r) => {
        if (state.reprintStatusFilter === 'DECLINED') {
          return r.status === 'DECLINED' || r.status === 'REJECTED';
        }
        return r.status === state.reprintStatusFilter;
      });
    }

    elements.reprintsTableBody.innerHTML = '';

    if (filtered.length === 0) {
      elements.reprintsTableBody.innerHTML = `
        <tr>
          <td colspan="5" class="py-8 text-center text-slate-500">
            ${state.reprints.length === 0 ? 'No reprint requests currently tracked for this project.' : 'No reprint requests match filter.'}
          </td>
        </tr>
      `;
      return;
    }

    filtered.forEach((r) => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-800/40 transition';

      // Corresponding paper
      const paper = state.papers.find((p) => p.id === r.paper_id);
      const paperTitle = paper ? paper.title : r.paper_id;

      // Status pill color
      const statusColor =
        r.status === 'RECEIVED'
          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
          : r.status === 'SENT'
          ? 'bg-blue-500/20 text-blue-300 border-blue-500/30'
          : r.status === 'DECLINED' || r.status === 'REJECTED'
          ? 'bg-red-500/20 text-red-300 border-red-500/30'
          : 'bg-amber-500/20 text-amber-300 border-amber-500/30';

      tr.innerHTML = `
        <td class="py-3 px-4">
          <div class="font-semibold text-slate-200 line-clamp-2">${escapeHtml(paperTitle)}</div>
          <div class="font-mono text-[10px] text-indigo-400 mt-1">${escapeHtml(r.paper_id)}</div>
        </td>
        <td class="py-3 px-4">
          <div class="font-medium text-slate-200">${escapeHtml(r.author_name || 'Corresponding Author')}</div>
          <div class="text-[10px] text-slate-400 truncate max-w-[180px]">${escapeHtml(r.author_affiliation || 'Unknown Institution')}</div>
        </td>
        <td class="py-3 px-4">
          <div class="flex items-center gap-1.5">
            <input type="email" value="${escapeHtml(r.author_email || '')}" placeholder="author@univ.edu" class="reprint-email-input flex-1 bg-slate-950 text-slate-200 text-xs px-2.5 py-1.5 rounded border border-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono">
            <button class="btn-save-email px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded border border-slate-700 text-[11px] transition" title="Save updated email">
              Save
            </button>
          </div>
        </td>
        <td class="py-3 px-3">
          <select class="reprint-status-select bg-slate-950 text-xs rounded border border-slate-700 px-2 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500">
            <option value="DRAFT_READY" ${r.status === 'DRAFT_READY' ? 'selected' : ''}>DRAFT_READY</option>
            <option value="SENT" ${r.status === 'SENT' ? 'selected' : ''}>SENT</option>
            <option value="RECEIVED" ${r.status === 'RECEIVED' ? 'selected' : ''}>RECEIVED</option>
            <option value="DECLINED" ${r.status === 'DECLINED' || r.status === 'REJECTED' ? 'selected' : ''}>DECLINED</option>
          </select>
        </td>
        <td class="py-3 px-4 text-right space-x-1.5">
          <a href="${escapeHtml(r.mailto_url || '#')}" class="inline-flex items-center gap-1 px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[11px] transition font-medium" target="_blank" title="Launch default email client">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            Mailto:
          </a>
          <button class="btn-copy-draft px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded border border-slate-700 text-[11px] transition" title="Copy draft request to clipboard">
            Copy
          </button>
          <button class="btn-ingest-reprint px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded border border-slate-700 text-[11px] transition" title="Ingest acquired PDF">
            PDF
          </button>
        </td>
      `;

      // Wire inline email save
      const emailInput = tr.querySelector('.reprint-email-input');
      const saveBtn = tr.querySelector('.btn-save-email');
      const doSaveEmail = () => {
        const val = emailInput.value.trim();
        if (val !== (r.author_email || '')) {
          updateReprintEmail(r.id, val);
        }
      };
      saveBtn.addEventListener('click', doSaveEmail);
      emailInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') doSaveEmail();
      });

      // Wire status change
      const statusSelect = tr.querySelector('.reprint-status-select');
      statusSelect.addEventListener('change', () => {
        updateReprintStatus(r.id, statusSelect.value);
      });

      // Wire copy draft
      const copyBtn = tr.querySelector('.btn-copy-draft');
      copyBtn.addEventListener('click', () => {
        const fullDraft = `Subject: ${r.subject || 'Preprint reprint inquiry'}\n\n${r.body || ''}`;
        navigator.clipboard.writeText(fullDraft).then(
          () => showToast('Reprint draft copied to clipboard!', 'success'),
          () => showToast('Failed to copy to clipboard', 'error')
        );
      });

      // Wire ingest received PDF
      const ingestBtn = tr.querySelector('.btn-ingest-reprint');
      ingestBtn.addEventListener('click', () => {
        openIngestModal(r.paper_id);
      });

      elements.reprintsTableBody.appendChild(tr);
    });
  }

  // ---------------------------------------------------------------------------
  // Paper Details Drawer
  // ---------------------------------------------------------------------------
  function openDrawer(paper) {
    state.selectedPaper = paper;

    elements.drawerTitle.textContent = paper.title || 'Untitled Paper';
    elements.drawerVenueYear.textContent = `${paper.venue_name || 'Unknown Venue'}${paper.year ? `, ${paper.year}` : ''}`;

    const oaType = (paper.oa_status || 'closed').toLowerCase();
    elements.drawerOaBadge.textContent = `${oaType.toUpperCase()} OA`;
    elements.drawerOaBadge.className = `px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
      oaType === 'gold'
        ? 'bg-amber-500/20 text-amber-300'
        : oaType === 'green'
        ? 'bg-emerald-500/20 text-emerald-300'
        : oaType === 'hybrid'
        ? 'bg-blue-500/20 text-blue-300'
        : 'bg-slate-800 text-slate-400'
    }`;

    if (paper.is_retracted) {
      elements.drawerRetractedBadge.classList.remove('hidden');
    } else {
      elements.drawerRetractedBadge.classList.add('hidden');
    }

    elements.drawerDoi.textContent = paper.doi || paper.id || '-';
    elements.drawerCitations.textContent = `${paper.citation_count || 0} citations (${paper.influential_citation_count || 0} influential)`;
    elements.drawerGaps.textContent = `${paper.gap_count || 0} documented gaps`;
    elements.drawerLocalPdf.textContent = paper.local_pdf_path || (paper.has_pdf ? 'Available' : 'None');

    // Authors
    elements.drawerAuthorsList.innerHTML = '';
    if (paper.authors && paper.authors.length > 0) {
      paper.authors.forEach((author) => {
        const div = document.createElement('div');
        div.className = 'bg-slate-950/40 p-2 rounded border border-slate-800 flex justify-between items-center';
        div.innerHTML = `
          <div>
            <div class="font-medium text-slate-200">${escapeHtml(author.name)}</div>
            ${author.institution ? `<div class="text-[10px] text-slate-400">${escapeHtml(author.institution)}</div>` : ''}
          </div>
          ${author.email ? `<a href="mailto:${escapeHtml(author.email)}" class="text-indigo-400 hover:underline text-[11px] font-mono">${escapeHtml(author.email)}</a>` : ''}
        `;
        elements.drawerAuthorsList.appendChild(div);
      });
    } else {
      elements.drawerAuthorsList.innerHTML = '<p class="text-slate-500">No author records available.</p>';
    }

    // Abstract
    elements.drawerAbstract.textContent = paper.abstract || 'No abstract text available for this record.';

    // Drawer Buttons
    elements.drawerBtnViewPdf.onclick = () => {
      if (paper.local_pdf_path) {
        showToast(`Local copy stored at: ${paper.local_pdf_path}`, 'info');
      } else if (paper.pdf_url) {
        window.open(paper.pdf_url, '_blank');
      } else {
        showToast('No PDF currently linked. Click Ingest to store a copy.', 'info');
      }
    };

    elements.drawerBtnIngestPdf.onclick = () => {
      openIngestModal(paper.id);
    };

    // Open animations
    elements.drawerBackdrop.classList.remove('backdrop-hidden');
    elements.drawerBackdrop.classList.add('backdrop-visible');
    elements.paperDrawer.classList.remove('drawer-closed');
    elements.paperDrawer.classList.add('drawer-open');
  }

  function closeDrawer() {
    elements.drawerBackdrop.classList.remove('backdrop-visible');
    elements.drawerBackdrop.classList.add('backdrop-hidden');
    elements.paperDrawer.classList.remove('drawer-open');
    elements.paperDrawer.classList.add('drawer-closed');
  }

  // ---------------------------------------------------------------------------
  // PDF Ingestion Modal
  // ---------------------------------------------------------------------------
  function openIngestModal(paperId) {
    elements.modalPaperId.value = paperId;
    elements.modalPdfPath.value = '';
    elements.ingestModal.classList.remove('hidden');
    elements.modalPdfPath.focus();
  }

  function closeIngestModal() {
    elements.ingestModal.classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // Tab Switching
  // ---------------------------------------------------------------------------
  function switchTab(target) {
    state.activeTab = target;

    const tabs = [
      { id: 'network', btn: elements.tabBtnNetwork, view: elements.viewNetwork },
      { id: 'papers', btn: elements.tabBtnPapers, view: elements.viewPapers },
      { id: 'reprints', btn: elements.tabBtnReprints, view: elements.viewReprints },
    ];

    tabs.forEach((t) => {
      if (t.id === target) {
        t.btn.classList.remove('border-transparent', 'text-slate-400');
        t.btn.classList.add('border-indigo-500', 'text-indigo-400');
        t.view.classList.remove('hidden');
      } else {
        t.btn.classList.remove('border-indigo-500', 'text-indigo-400');
        t.btn.classList.add('border-transparent', 'text-slate-400');
        t.view.classList.add('hidden');
      }
    });

    if (target === 'network' && state.network) {
      setTimeout(() => {
        state.network.redraw();
        state.network.fit({ animation: false });
      }, 50);
    }
  }

  // ---------------------------------------------------------------------------
  // Event Listeners Initialization
  // ---------------------------------------------------------------------------
  function initListeners() {
    // Project switcher
    elements.projectsDropdown.addEventListener('change', (e) => {
      selectProject(e.target.value);
    });

    // Session / Graph Scope picker
    elements.sessionSelector.addEventListener('change', () => {
      if (state.currentProjectId) {
        loadProjectData(state.currentProjectId);
      }
    });

    // Refresh button
    elements.btnRefresh.addEventListener('click', () => {
      if (state.currentProjectId) {
        loadProjectData(state.currentProjectId);
      } else {
        fetchProjects();
      }
    });

    // Tab buttons
    elements.tabBtnNetwork.addEventListener('click', () => switchTab('network'));
    elements.tabBtnPapers.addEventListener('click', () => switchTab('papers'));
    elements.tabBtnReprints.addEventListener('click', () => switchTab('reprints'));

    // Network Controls
    elements.btnZoomIn.addEventListener('click', () => {
      if (state.network) {
        state.network.moveTo({ scale: state.network.getScale() * 1.3 });
      }
    });

    elements.btnZoomOut.addEventListener('click', () => {
      if (state.network) {
        state.network.moveTo({ scale: state.network.getScale() / 1.3 });
      }
    });

    elements.btnZoomFit.addEventListener('click', () => {
      if (state.network) {
        state.network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
      }
    });

    elements.btnTogglePhysics.addEventListener('click', () => {
      state.physicsEnabled = !state.physicsEnabled;
      if (state.network) {
        state.network.setOptions({ physics: { enabled: state.physicsEnabled } });
      }
      elements.physicsIndicator.className = `w-1.5 h-1.5 rounded-full ${
        state.physicsEnabled ? 'bg-emerald-400' : 'bg-slate-500'
      }`;
    });

    // Papers table search & filters
    elements.papersSearchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value;
      renderPapersTable();
    });

    elements.papersFilterOa.addEventListener('change', (e) => {
      state.oaFilter = e.target.value;
      renderPapersTable();
    });

    elements.papersSort.addEventListener('change', (e) => {
      state.sortField = e.target.value;
      renderPapersTable();
    });

    // Reprints table filters
    elements.reprintsFilterStatus.addEventListener('change', (e) => {
      state.reprintStatusFilter = e.target.value;
      renderReprintsTable();
    });

    // Drawer close handlers
    elements.drawerCloseBtn.addEventListener('click', closeDrawer);
    elements.drawerBackdrop.addEventListener('click', closeDrawer);

    // Modal handlers
    elements.modalCloseBtn.addEventListener('click', closeIngestModal);
    elements.modalCancelBtn.addEventListener('click', closeIngestModal);
    elements.modalSubmitBtn.addEventListener('click', () => {
      const pid = elements.modalPaperId.value;
      const path = elements.modalPdfPath.value;
      if (!path.trim()) {
        showToast('Please enter an absolute PDF file path', 'error');
        return;
      }
      submitIngestPdf(pid, path);
    });

    // Keyboard shortcuts (Escape closes drawer & modal)
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeDrawer();
        closeIngestModal();
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    initListeners();
    fetchProjects();
  });
})();
