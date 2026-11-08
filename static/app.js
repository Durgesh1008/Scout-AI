// Scout AI — Modern JavaScript Client

let currentSection = 'jobs';
let conversationHistory = [];
let currentTodoFilter = 'all';

// Navigation delegation — ensures every nav link & hash link works instantly
document.addEventListener('click', (e) => {
  const link = e.target.closest('a[href^="#"], [data-section]');
  if (link) {
    const section = link.dataset.section || link.getAttribute('href')?.replace('#', '');
    if (section && document.getElementById(`view-${section}`)) {
      e.preventDefault();
      navigateTo(section);
    }
  }
});

function navigateTo(section) {
  if (!section) section = 'jobs';
  currentSection = section;

  // Persist view state in URL hash & localStorage so reloads never kick the user to home
  window.location.hash = section;
  try {
    localStorage.setItem('scout_active_view', section);
  } catch (e) {}

  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.querySelectorAll(`.nav-link[data-section="${section}"]`).forEach(l => l.classList.add('active'));

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const targetView = document.getElementById(`view-${section}`);
  if (targetView) targetView.classList.add('active');

  if ((section === 'interview' || section === 'prep') && !currentMockQuestion) {
    generateNewMockQuestion();
  }

  closeSidebar();
}

function reloadOnSection(section = 'jobs', delay = 1000) {
  window.location.hash = section;
  try {
    localStorage.setItem('scout_active_view', section);
  } catch (e) {}
  setTimeout(() => window.location.reload(), delay);
}

// Mobile sidebar & top nav menu toggle
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebar-overlay');

document.querySelectorAll('.menu-btn, #menu-toggle').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('open');
  });
});

if (overlay) overlay.addEventListener('click', closeSidebar);

function closeSidebar() {
  if (sidebar) sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('open');
}

// Toast notifications
const toastEl = document.getElementById('app-toast');
const toastText = document.getElementById('toast-text');
let toastInstance = null;

function toast(message, type = 'info') {
  if (!toastEl || !toastText) return;
  toastText.textContent = message;
  toastEl.className = `toast text-bg-${type}`;
  if (!toastInstance) toastInstance = new bootstrap.Toast(toastEl, { delay: 3500 });
  toastInstance.show();
}

// HTTP helpers
async function apiPost(url, data = {}) {
  const body = new URLSearchParams(data).toString();
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Request failed');
  return result;
}

async function apiGet(url) {
  const response = await fetch(url);
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Request failed');
  return result;
}

// -------------------------------------------------------------
// CHAT FUNCTIONALITY (FAST RESPONSE ENGINE)
// -------------------------------------------------------------
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatMessages = document.getElementById('chat-messages');

if (chatInput) {
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChat(e);
    }
  });

  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 150) + 'px';
  });
}

function quickAction(text) {
  if (chatInput) {
    chatInput.value = text;
    chatInput.focus();
    sendChat();
  }
}

async function sendChat(event) {
  if (event) event.preventDefault();

  const input = document.getElementById('chat-input');
  if (!input) return;

  const text = input.value.trim();
  if (!text) return;

  const welcomeCard = document.getElementById('welcome-card');
  if (welcomeCard) welcomeCard.remove();

  addMessage(text, 'user');
  input.value = '';
  input.style.height = 'auto';

  const loadingId = 'loading-' + Date.now();
  addLoadingMessage(loadingId);

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Request failed');

    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) loadingEl.remove();

    addMessage(data.reply, 'assistant');

    if (text.toLowerCase().includes('todo') || text.toLowerCase().includes('task')) {
      loadTodos();
    }
  } catch (error) {
    const loadingEl = document.getElementById(loadingId);
    if (loadingEl) loadingEl.remove();
    addMessage(`Error: ${error.message}`, 'assistant', true);
  }
}

function addMessage(text, type, isError = false) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${type}`;
  if (isError) bubble.style.borderLeft = '3px solid var(--accent-danger)';
  bubble.innerHTML = formatMarkdown(text);
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addLoadingMessage(id) {
  const bubble = document.createElement('div');
  bubble.id = id;
  bubble.className = 'chat-bubble assistant loading';
  bubble.innerHTML = `<div class="thinking-dots"><span></span><span></span><span></span></div> Thinking...`;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function clearChat() {
  conversationHistory = [];
  chatMessages.innerHTML = `
    <div class="welcome-card" id="welcome-card">
      <div class="welcome-icon">⚡</div>
      <h3>Hi there! I'm Scout.</h3>
      <p class="muted mb-3">Your local autonomous agent is ready.</p>
    </div>
  `;
}

// -------------------------------------------------------------
// RESUME MANAGEMENT (ANYONE CAN UPLOAD & MATCH)
// -------------------------------------------------------------
async function processResumeFile(file, statusEl = null) {
  if (!file) return;

  toast(`Uploading ${file.name} and matching jobs...`, 'info');
  if (statusEl) {
    statusEl.style.display = 'block';
    statusEl.className = 'alert alert-info mt-3';
    statusEl.innerHTML = `<div class="spinner-border spinner-border-sm me-2"></div> Uploading <strong>${escapeHtml(file.name)}</strong> and calculating match scores...`;
  }

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/api/resume', { method: 'POST', body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Resume upload failed');

    toast(`Resume active! Re-scored ${result.jobs_rescored} jobs!`, 'success');

    if (statusEl) {
      statusEl.className = 'alert alert-success mt-3';
      statusEl.innerHTML = `<strong>Success!</strong> ${escapeHtml(result.filename)} is now active (${result.jobs_rescored} opportunities re-scored).`;
    }

    // Refresh and stay on the current section
    reloadOnSection(currentSection || 'resume', 1000);
  } catch (error) {
    if (statusEl) {
      statusEl.className = 'alert alert-danger mt-3';
      statusEl.textContent = `Upload failed: ${error.message}`;
    }
    toast(error.message, 'danger');
  }
}

async function handleResumeUpload(event) {
  const file = event.target?.files?.[0];
  if (file) await processResumeFile(file);
}

async function handleDedicatedResumeUpload(event) {
  const file = event.target?.files?.[0];
  const statusEl = document.getElementById('dedicated-upload-status');
  if (file) await processResumeFile(file, statusEl);
}

async function uploadResume(event) {
  if (event) event.preventDefault();
  const input = document.getElementById('resume-file');
  if (!input || !input.files[0]) return;
  const status = document.getElementById('resume-message');
  await processResumeFile(input.files[0], status);
}

async function switchResume(path) {
  if (!path) return;
  toast('Switching active resume & re-scoring...', 'info');

  try {
    const result = await apiPost('/api/resume/select', { path });
    toast(`Switched to ${result.active_resume}! ${result.jobs_rescored} jobs re-scored.`, 'success');
    reloadOnSection('jobs', 1000);
  } catch (error) {
    toast(error.message, 'danger');
  }
}

async function rescoreJobs() {
  toast('Re-scoring all jobs against active resume (India + Remote, 0-2 yrs)...', 'info');
  try {
    const result = await apiPost('/api/jobs/rescore');
    if (result.success) {
      toast(`Re-scored ${result.jobs_rescored} jobs for ${result.resume_name}!`, 'success');
      reloadOnSection('jobs', 1000);
    } else {
      toast(result.error || 'Failed to rescore', 'danger');
    }
  } catch (error) {
    toast(error.message, 'danger');
  }
}

// -------------------------------------------------------------
// TODO / TASK MANAGER
// -------------------------------------------------------------
async function loadTodos() {
  try {
    const data = await apiGet('/api/tasks');
    renderTodos(data.tasks || []);
  } catch (error) {
    console.error('Failed to load todos:', error);
  }
}

function renderTodos(todos) {
  const list = document.getElementById('todo-list');
  if (!list) return;

  if (!todos || todos.length === 0) {
    list.innerHTML = `<div class="empty-state"><i class="bi bi-check2-square display-3 text-muted"></i><p>No todos yet. Add your first goal above!</p></div>`;
    updateTodoStats(0, 0);
    return;
  }

  let pending = 0;
  let completed = 0;

  list.innerHTML = todos.map(todo => {
    if (todo.completed) completed++; else pending++;

    const isHidden = (currentTodoFilter === 'pending' && todo.completed) ||
                     (currentTodoFilter === 'completed' && !todo.completed);

    return `
      <div class="task-item ${todo.completed ? 'completed' : ''}" data-id="${todo.id}" data-completed="${todo.completed}" style="${isHidden ? 'display:none;' : ''}">
        <label class="form-check mb-0">
          <input class="form-check-input todo-check" type="checkbox" ${todo.completed ? 'checked' : ''} onchange="toggleTodo(${todo.id}, this.checked)">
          <span class="form-check-label ${todo.completed ? 'text-decoration-line-through text-muted' : ''}">${escapeHtml(todo.title)}</span>
        </label>
        <button class="btn btn-sm btn-outline-danger btn-delete" onclick="deleteTodo(${todo.id})" title="Delete todo"><i class="bi bi-trash"></i></button>
      </div>
    `;
  }).join('');

  updateTodoStats(pending, completed);
}

function updateTodoStats(pending, completed) {
  const counter = document.getElementById('todo-counter');
  if (counter) {
    counter.textContent = `${pending} pending, ${completed} completed`;
  }
}

async function addTodo(event) {
  if (event) event.preventDefault();
  const input = document.getElementById('todo-input');
  if (!input) return;

  const title = input.value.trim();
  if (!title) {
    toast('Please enter a todo description', 'warning');
    return;
  }

  try {
    const result = await apiPost('/api/tasks', { title });
    input.value = '';
    toast('Todo added!', 'success');
    loadTodos();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

async function toggleTodo(taskId, completed) {
  try {
    await apiPost(`/api/tasks/${taskId}/toggle`, { completed });
    const item = document.querySelector(`.task-item[data-id="${taskId}"]`);
    if (item) {
      item.dataset.completed = completed;
      item.classList.toggle('completed', completed);
      const label = item.querySelector('.form-check-label');
      if (label) {
        label.classList.toggle('text-decoration-line-through', completed);
        label.classList.toggle('text-muted', completed);
      }
    }
    toast(completed ? 'Todo completed!' : 'Todo marked active', 'success');
    updateTodoCountersFromDOM();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

async function deleteTodo(taskId) {
  try {
    const res = await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete');

    const item = document.querySelector(`.task-item[data-id="${taskId}"]`);
    if (item) item.remove();
    toast('Todo removed', 'info');
    updateTodoCountersFromDOM();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

async function clearCompletedTodos() {
  try {
    const res = await apiPost('/api/tasks/clear-completed');
    toast(`Cleared ${res.deleted} completed todos`, 'success');
    loadTodos();
  } catch (error) {
    toast(error.message, 'danger');
  }
}

function filterTodos(filter) {
  currentTodoFilter = filter;
  ['all', 'pending', 'completed'].forEach(f => {
    const btn = document.getElementById(`filter-${f}`);
    if (btn) btn.classList.toggle('active', f === filter);
  });

  const items = document.querySelectorAll('.task-item');
  items.forEach(item => {
    const isCompleted = item.dataset.completed === 'true';
    if (filter === 'all') {
      item.style.display = '';
    } else if (filter === 'pending') {
      item.style.display = isCompleted ? 'none' : '';
    } else if (filter === 'completed') {
      item.style.display = isCompleted ? '' : 'none';
    }
  });
}

function updateTodoCountersFromDOM() {
  const items = document.querySelectorAll('.task-item');
  let completed = 0;
  let pending = 0;
  items.forEach(i => {
    if (i.dataset.completed === 'true') completed++; else pending++;
  });
  updateTodoStats(pending, completed);
}

// -------------------------------------------------------------
// JOB HUNTING & OUTREACH
// -------------------------------------------------------------
async function huntJobs() {
  const msgEl = document.getElementById('job-message');
  if (msgEl) {
    msgEl.style.display = 'block';
    msgEl.className = 'alert alert-info mt-3';
    msgEl.innerHTML = '<div class="spinner-border spinner-border-sm me-2"></div> Fetching India & Remote jobs (0-2 years)...';
  }

  try {
    const result = await apiPost('/api/jobs/hunt');
    if (msgEl) {
      msgEl.className = 'alert alert-success mt-3';
      msgEl.innerHTML = `<strong>Search complete!</strong> Added ${result.added} new jobs matching your profile.`;
    }
    toast(`Found ${result.added} new matching jobs!`, 'success');
    // Stay strictly on the Jobs view upon reload
    reloadOnSection('jobs', 1200);
  } catch (error) {
    if (msgEl) {
      msgEl.className = 'alert alert-danger mt-3';
      msgEl.textContent = `Error: ${error.message}`;
    }
    toast('Job search failed', 'danger');
  }
}

function resetJobFilters() {
  const searchInput = document.getElementById('job-search');
  const roleSelect = document.getElementById('job-role-filter');
  const locSelect = document.getElementById('job-location-filter');
  const statusSelect = document.getElementById('job-status-filter');
  const sourceSelect = document.getElementById('job-source-filter');

  if (searchInput) searchInput.value = '';
  if (roleSelect) roleSelect.value = '';
  if (locSelect) locSelect.value = 'india_remote';
  if (statusSelect) statusSelect.value = '';
  if (sourceSelect) sourceSelect.value = '';

  filterJobs();
}

function filterJobs() {
  const searchTerm = (document.getElementById('job-search')?.value || '').toLowerCase().trim();
  const roleFilter = (document.getElementById('job-role-filter')?.value || '').toLowerCase().trim();
  const locationFilter = document.getElementById('job-location-filter')?.value || 'india_remote';
  const statusFilter = document.getElementById('job-status-filter')?.value || '';
  const sourceFilter = (document.getElementById('job-source-filter')?.value || '').toLowerCase().trim();

  const cards = document.querySelectorAll('.job-card');
  let visibleCount = 0;

  cards.forEach(card => {
    const title = (card.dataset.title || '').toLowerCase();
    const company = (card.dataset.company || '').toLowerCase();
    const source = (card.dataset.source || '').toLowerCase();
    const status = card.dataset.status || '';
    const cardRoleStr = (card.dataset.role || '').toLowerCase();
    const cardRoles = cardRoleStr.split(/\s+/).filter(Boolean);
    const locCategory = (card.dataset.locationCategory || '').toLowerCase();
    const isRemote = card.dataset.remote === 'true';

    const matchesSearch = !searchTerm || title.includes(searchTerm) || company.includes(searchTerm);
    const matchesRole = !roleFilter || cardRoles.includes(roleFilter);
    const matchesStatus = !statusFilter || status === statusFilter;
    const matchesSource = !sourceFilter || source === sourceFilter || (sourceFilter === 'jsearch' && (source === 'wellfound' || source === 'jsearch'));

    let matchesLocation = true;
    if (locationFilter === 'india_remote') {
      matchesLocation = (locCategory === 'india' || locCategory === 'remote' || isRemote);
    } else if (locationFilter === 'india_only') {
      matchesLocation = (locCategory === 'india');
    } else if (locationFilter === 'remote_only') {
      matchesLocation = (locCategory === 'remote' || isRemote);
    } else if (locationFilter === 'out_of_india') {
      matchesLocation = (locCategory === 'out_of_india');
    } else if (locationFilter === 'all') {
      matchesLocation = true;
    }

    const isVisible = matchesSearch && matchesRole && matchesStatus && matchesSource && matchesLocation;
    card.style.display = isVisible ? '' : 'none';
    if (isVisible) visibleCount++;
  });

  const statsEl = document.getElementById('job-stats');
  if (statsEl) {
    statsEl.style.display = 'block';
    const countEl = document.getElementById('visible-count');
    if (countEl) countEl.textContent = visibleCount;
  }

  const noResultsEl = document.getElementById('no-filter-results');
  if (noResultsEl) {
    noResultsEl.style.display = (visibleCount === 0 && cards.length > 0) ? 'block' : 'none';
  }
}

function setupResumeDropzone() {
  const dropzone = document.getElementById('resume-dropzone-box');
  if (!dropzone) return;

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('drag-over');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('drag-over');
    }, false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      const statusEl = document.getElementById('dedicated-upload-status');
      processResumeFile(files[0], statusEl);
    }
  }, false);
}

async function updateJobStatus(jobId, status) {
  try {
    await apiPost(`/api/jobs/${jobId}/status`, { status });
    toast('Status updated', 'success');
  } catch (error) {
    toast(error.message, 'danger');
  }
}

async function makeDraft(jobId) {
  toast('Drafting personalized pitch with AI...', 'info');
  try {
    const result = await apiPost(`/api/jobs/${jobId}/draft`);
    const gmailCreated = result.gmail && result.gmail.created;
    toast(gmailCreated ? 'Draft created in your Gmail account!' : 'Draft saved locally in data/drafts/', 'success');

    const win = window.open('', '_blank');
    if (win) {
      win.document.write(`
        <html><head><title>Cold Outreach Draft</title>
        <style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;padding:30px;background:#0d1117;color:#e6edf3;max-width:700px;margin:0 auto;}
        pre{background:#161b22;padding:16px;border-radius:8px;border:1px solid #30363d;white-space:pre-wrap;font-size:14px;line-height:1.6;color:#58a6ff;}
        .badge{background:#238636;color:#fff;padding:4px 8px;border-radius:4px;font-size:12px;font-weight:600;}
        </style></head><body>
        <h2>Email Outreach Draft ${gmailCreated ? '<span class="badge">Created in Gmail Drafts</span>' : ''}</h2>
        <p><strong>Subject:</strong> ${escapeHtml(result.subject)}</p>
        <pre>${escapeHtml(result.body)}</pre>
        <p style="color:#8b949e;font-size:12px;">Saved locally at: ${escapeHtml(result.path)}</p>
        </body></html>
      `);
      win.document.close();
    }
  } catch (error) {
    toast('Failed to draft: ' + error.message, 'danger');
  }
}

// -------------------------------------------------------------
// HABIT MANAGEMENT & BRIEFING
// -------------------------------------------------------------
async function toggleHabit(habitId, completed) {
  try {
    await apiPost(`/api/habits/${habitId}`, { completed });
    toast(completed ? 'Habit completed!' : 'Habit unchecked', 'success');
  } catch (error) {
    toast(error.message, 'danger');
  }
}

async function makeBriefing() {
  const output = document.getElementById('briefing-output');
  if (!output) return;

  output.style.display = 'block';
  output.innerHTML = '<div class="thinking-dots"><span></span><span></span><span></span></div> Generating executive briefing...';

  try {
    const result = await apiPost('/api/briefing');
    output.innerHTML = formatMarkdown(result.briefing);
    toast('Briefing ready!', 'success');
  } catch (error) {
    output.innerHTML = `<div class="alert alert-danger">${escapeHtml(error.message)}</div>`;
  }
}

// -------------------------------------------------------------
// PREP LAB & STUDY HUB
// -------------------------------------------------------------
let currentModalIntel = null;

function filterPrepTracks(trackId, pillEl) {
  if (pillEl) {
    document.querySelectorAll('.prep-filter-pill').forEach(p => p.classList.remove('active'));
    pillEl.classList.add('active');
  }

  const trackItems = document.querySelectorAll('.prep-track-item');
  trackItems.forEach(item => {
    if (trackId === 'all' || item.dataset.trackId === trackId) {
      item.style.display = '';
    } else {
      item.style.display = 'none';
    }
  });
}

function searchCompanyPrep(query) {
  const q = (query || '').toLowerCase().trim();
  const items = document.querySelectorAll('.company-grid-item');
  items.forEach(item => {
    const name = (item.dataset.name || '').toLowerCase();
    item.style.display = (!q || name.includes(q)) ? '' : 'none';
  });
}

function toggleQA(headerEl) {
  const bodyEl = headerEl.nextElementSibling;
  const iconEl = headerEl.querySelector('.transition-icon');
  if (!bodyEl) return;

  const isExpanded = bodyEl.style.display !== 'none';
  bodyEl.style.display = isExpanded ? 'none' : 'block';
  if (iconEl) {
    iconEl.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(180deg)';
  }
}

async function openCompanyPrep(companyName, roleTitle = '') {
  if (!companyName) return;

  const modalEl = document.getElementById('company-prep-modal');
  if (!modalEl) return;

  const bsModal = new bootstrap.Modal(modalEl);
  bsModal.show();

  const loadingEl = document.getElementById('modal-prep-loading');
  const contentEl = document.getElementById('modal-prep-content');
  const titleEl = document.getElementById('modal-company-title');
  const avatarEl = document.getElementById('modal-company-avatar');
  const badgeEl = document.getElementById('modal-company-badge');
  const diffEl = document.getElementById('modal-company-difficulty');
  const roundsContainer = document.getElementById('modal-rounds-container');
  const grillContainer = document.getElementById('modal-grill-container');
  const questionsContainer = document.getElementById('modal-questions-container');
  const tipText = document.getElementById('modal-tip-text');

  if (loadingEl) loadingEl.style.display = 'block';
  if (contentEl) contentEl.style.display = 'none';
  if (titleEl) titleEl.textContent = companyName;
  if (avatarEl) avatarEl.textContent = companyName.charAt(0).toUpperCase();

  try {
    const encoded = encodeURIComponent(companyName.trim());
    const res = await fetch(`/api/prep/company/${encoded}`);
    if (!res.ok) throw new Error('Failed to load company prep details');
    const data = await res.json();
    const intel = data.intel;
    currentModalIntel = intel;

    if (badgeEl) badgeEl.textContent = intel.badge || 'Technology';
    if (diffEl) {
      diffEl.textContent = intel.difficulty || 'Medium';
      diffEl.className = intel.difficulty === 'Hard' ? 'badge bg-danger' : 'badge bg-warning text-dark';
    }

    // Populate Rounds
    if (roundsContainer) {
      roundsContainer.innerHTML = (intel.rounds || []).map((r, i) => `
        <div class="round-timeline-step">
          <div class="round-timeline-node">${i + 1}</div>
          <h6 class="fw-bold text-white mb-1">${escapeHtml(r.round)} — ${escapeHtml(r.type)}</h6>
          <p class="small text-muted mb-0">${escapeHtml(r.focus)}</p>
        </div>
      `).join('');
    }

    // Populate What They Grill On
    if (grillContainer) {
      grillContainer.innerHTML = (intel.what_they_grill || []).map(g => `
        <div class="d-flex align-items-start gap-2 mb-2">
          <i class="bi bi-arrow-right-short text-warning fs-5"></i>
          <span class="small text-light">${escapeHtml(g)}</span>
        </div>
      `).join('');
    }

    // Populate Repeated Questions
    if (questionsContainer) {
      questionsContainer.innerHTML = (intel.repeated_questions || []).map((q, idx) => `
        <div class="p-2 px-3 rounded-2 border border-secondary small text-light" style="background: rgba(13,17,23,0.5);">
          <strong class="text-info me-2">Q${idx + 1}:</strong> ${escapeHtml(q)}
        </div>
      `).join('');
    }

    // Populate Real LeetCode Problems (liquidslr dataset)
    const leetcodeSection = document.getElementById('modal-leetcode-section');
    const leetcodeTbody = document.getElementById('modal-leetcode-tbody');
    const problems = intel.leetcode_problems || [];
    if (leetcodeTbody && problems.length > 0) {
      if (leetcodeSection) leetcodeSection.style.display = 'block';
      leetcodeTbody.innerHTML = problems.map((p, idx) => `
        <tr class="border-secondary ${idx >= 4 ? 'modal-lc-extra d-none' : ''}">
          <td class="text-muted fw-bold">#${escapeHtml(p.id)}</td>
          <td>
            <span class="fw-bold text-white">${escapeHtml(p.title)}</span>
            <span class="text-muted small ms-2 d-none d-md-inline">(${escapeHtml(p.acceptance || 'OA Tagged')})</span>
          </td>
          <td>
            <span class="badge ${p.difficulty === 'Hard' ? 'bg-danger' : (p.difficulty === 'Medium' ? 'bg-warning text-dark' : 'bg-success')}">${escapeHtml(p.difficulty)}</span>
          </td>
          <td>
            <span class="badge bg-dark border border-secondary text-info">${escapeHtml(p.pattern || 'DSA')}</span>
          </td>
          <td class="text-end">
            <div class="d-inline-flex gap-1 justify-content-end">
              <button type="button" class="btn btn-sm btn-outline-success py-1 px-2" style="font-size: 11px;" title="Solve in Mock Studio" onclick="loadLeetCodeProblemIntoMock('${p.id}', '${escapeHtml(intel.name)}')">
                <i class="bi bi-play-circle me-1"></i>Studio
              </button>
              <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener" class="btn btn-sm btn-outline-primary py-1 px-2" style="font-size: 11px;" title="Open on LeetCode">
                <i class="bi bi-box-arrow-up-right"></i>
              </a>
            </div>
          </td>
        </tr>
      `).join('');

      // Show/hide toggle button if more than 4 problems
      const toggleWrapper = document.getElementById('modal-leetcode-toggle-wrapper');
      const toggleBtnText = document.getElementById('modal-lc-toggle-text');
      const toggleBtnIcon = document.getElementById('modal-lc-toggle-icon');
      if (toggleWrapper) {
        if (problems.length > 4) {
          toggleWrapper.style.display = 'block';
          if (toggleBtnText) toggleBtnText.textContent = `Show All Problems (${problems.length - 4} More)`;
          if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-down me-1';
        } else {
          toggleWrapper.style.display = 'none';
        }
      }
    } else if (leetcodeSection) {
      leetcodeSection.style.display = 'none';
    }

    if (tipText) {
      tipText.textContent = intel.insider_tips || 'Research the company tech stack and practice explaining your code aloud.';
    }

    if (loadingEl) loadingEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'block';

  } catch (err) {
    if (loadingEl) loadingEl.style.display = 'none';
    toast('Error loading company intel: ' + err.message, 'danger');
  }
}

function copyCompanyIntel() {
  if (!currentModalIntel) return;
  const intel = currentModalIntel;
  const lines = [
    `🏢 ${intel.name} Interview Cheatsheet (${intel.badge})`,
    `Difficulty: ${intel.difficulty}`,
    '',
    '📌 HIRING ROUNDS:'
  ];
  (intel.rounds || []).forEach(r => lines.push(`• ${r.round} (${r.type}): ${r.focus}`));
  lines.push('', '🔥 WHAT THEY GRILL CANDIDATES ON:');
  (intel.what_they_grill || []).forEach(g => lines.push(`• ${g}`));
  lines.push('', '💬 RECENT INTERVIEW QUESTIONS:');
  (intel.repeated_questions || []).forEach((q, i) => lines.push(`${i + 1}. ${q}`));
  if (intel.insider_tips) {
    lines.push('', `💡 INSIDER TIP: ${intel.insider_tips}`);
  }

  navigator.clipboard.writeText(lines.join('\n'))
    .then(() => toast('Cheatsheet copied to clipboard!', 'success'))
    .catch(() => toast('Failed to copy to clipboard', 'warning'));
}

// -------------------------------------------------------------
// WORKFLOW 2: AI MOCK INTERVIEW SIMULATOR
// -------------------------------------------------------------
let currentMockTarget = 'swiggy';
let currentMockQuestion = null;

function selectMockTarget(btnEl) {
  if (!btnEl) return;
  document.querySelectorAll('#mock-target-chips button').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');
  currentMockTarget = btnEl.dataset.target || 'swiggy';
  generateNewMockQuestion();
}

function randomizeMockQuestion() {
  const chips = Array.from(document.querySelectorAll('#mock-target-chips button'));
  if (chips.length === 0) return;
  const randChip = chips[Math.floor(Math.random() * chips.length)];
  selectMockTarget(randChip);
}

function loadSystemDesignIntoMock(caseId) {
  currentMockTarget = 'systemdesign';
  document.querySelectorAll('#mock-target-chips button').forEach(b => {
    b.classList.toggle('active', b.dataset.target === 'systemdesign');
  });
  navigateTo('interview');
  setTimeout(() => {
    generateNewMockQuestion('systemdesign', caseId);
  }, 100);
}

function loadLeetCodeProblemIntoMock(qId, companyName) {
  const compClean = (companyName || '').toLowerCase().trim();
  currentMockTarget = compClean || 'swiggy';

  // Close modal if open
  const modalEl = document.getElementById('company-prep-modal');
  if (modalEl) {
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }

  // Update target chips
  document.querySelectorAll('#mock-target-chips button').forEach(b => {
    b.classList.toggle('active', b.dataset.target === currentMockTarget);
  });

  navigateTo('interview');
  setTimeout(() => {
    generateNewMockQuestion(currentMockTarget, null, qId);
  }, 120);
}

function startMockInterviewFromModal() {
  if (!currentModalIntel) return;
  const compName = (currentModalIntel.name || '').toLowerCase();
  currentMockTarget = compName;

  // Close modal
  const modalEl = document.getElementById('company-prep-modal');
  if (modalEl) {
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (modal) modal.hide();
  }

  // Navigate to dedicated interview view
  navigateTo('interview');
  setTimeout(() => {
    // Update active target chip if matching button exists
    document.querySelectorAll('#mock-target-chips button').forEach(b => {
      b.classList.toggle('active', b.dataset.target === compName);
    });
    generateNewMockQuestion(compName);
  }, 150);
}

async function generateNewMockQuestion(target, caseId, questionId) {
  const badgeEl = document.getElementById('mock-q-badge');
  const diffEl = document.getElementById('mock-q-diff');
  const titleEl = document.getElementById('mock-q-title');
  const textEl = document.getElementById('mock-q-text');
  const linkEl = document.getElementById('mock-q-link');
  const patternEl = document.getElementById('mock-q-pattern');
  const hintsListEl = document.getElementById('mock-hints-list');
  const evalResult = document.getElementById('mock-eval-result');
  const examplesWrapper = document.getElementById('mock-q-examples-wrapper');
  const examplesList = document.getElementById('mock-q-examples-list');
  const constraintsWrapper = document.getElementById('mock-q-constraints-wrapper');
  const constraintsList = document.getElementById('mock-q-constraints-list');
  const timeCompEl = document.getElementById('mock-q-time-complexity');
  const spaceCompEl = document.getElementById('mock-q-space-complexity');

  if (evalResult) evalResult.style.display = 'none';
  if (titleEl) titleEl.textContent = 'Generating real question...';

  const activeTarget = target || currentMockTarget;
  let apiUrl = `/api/mock/question?target=${encodeURIComponent(activeTarget)}`;
  if (caseId) apiUrl += `&case_id=${encodeURIComponent(caseId)}`;
  if (questionId) apiUrl += `&question_id=${encodeURIComponent(questionId)}`;

  try {
    const res = await fetch(apiUrl);
    if (!res.ok) throw new Error('Failed to load question');
    const data = await res.json();
    const q = data.question;
    currentMockQuestion = q;

    if (badgeEl) badgeEl.textContent = q.context_badge || `Target: ${activeTarget}`;
    if (diffEl) {
      diffEl.textContent = q.difficulty || 'Medium';
      diffEl.className = q.difficulty === 'Hard' ? 'badge bg-danger' : (q.difficulty === 'Easy' ? 'badge bg-success' : 'badge bg-warning text-dark');
    }
    if (titleEl) titleEl.textContent = q.title || 'Technical Question';
    if (textEl) textEl.textContent = q.description || q.question || '';

    if (linkEl) {
      if (q.url) {
        linkEl.href = q.url;
        linkEl.style.display = 'inline-block';
      } else {
        linkEl.style.display = 'none';
      }
    }

    if (patternEl) {
      if (q.pattern) {
        patternEl.innerHTML = `<i class="bi bi-tag me-1"></i> Pattern: ${escapeHtml(q.pattern)}`;
        patternEl.style.display = 'inline-block';
      } else {
        patternEl.style.display = 'none';
      }
    }

    // Complexity Box
    if (timeCompEl) {
      timeCompEl.textContent = q.target_complexity?.time || 'O(N)';
    }
    if (spaceCompEl) {
      spaceCompEl.textContent = q.target_complexity?.space || 'O(1)';
    }

    // Examples & Test Cases
    if (examplesWrapper && examplesList) {
      const exs = q.examples || [];
      if (exs.length > 0) {
        examplesWrapper.style.display = 'block';
        examplesList.innerHTML = exs.map((ex, idx) => `
          <div class="example-box">
            <div class="text-white-50 fw-bold mb-1" style="font-size: 11px;">Example ${idx + 1}:</div>
            <div class="text-light mb-1"><span class="text-info fw-bold">Input:</span> <code>${escapeHtml(ex.input || '')}</code></div>
            <div class="text-light mb-1"><span class="text-success fw-bold">Output:</span> <code>${escapeHtml(ex.output || '')}</code></div>
            ${ex.explanation ? `<div class="text-muted"><span class="text-warning fw-bold">Explanation:</span> ${escapeHtml(ex.explanation)}</div>` : ''}
          </div>
        `).join('');
      } else {
        examplesWrapper.style.display = 'none';
      }
    }

    // Constraints & Boundaries
    if (constraintsWrapper && constraintsList) {
      const cons = q.constraints || [];
      if (cons.length > 0) {
        constraintsWrapper.style.display = 'block';
        constraintsList.innerHTML = cons.map(c => `<li>${escapeHtml(c)}</li>`).join('');
      } else {
        constraintsWrapper.style.display = 'none';
      }
    }

    // Key Concepts & Bar Raiser Checklist
    if (hintsListEl) {
      const points = q.key_talking_points || q.keywords || [];
      hintsListEl.innerHTML = points.map(pt => `
        <span class="badge bg-dark border border-secondary text-light me-1 mb-1">${escapeHtml(pt)}</span>
      `).join('');
    }

    // Reset and automatically inject runnable starter code
    resetCodeTemplate();

  } catch (err) {
    toast('Error fetching mock question: ' + err.message, 'danger');
  }
}

function updateMockWordCount() {
  const text = (document.getElementById('mock-user-answer')?.value || '').trim();
  const words = text ? text.split(/\s+/).length : 0;
  const lines = text ? text.split('\n').length : 0;
  const countEl = document.getElementById('mock-word-count');
  if (countEl) countEl.textContent = `${words} words · ${lines} lines`;
}

function handleLanguageChange(lang) {
  const fnBadge = document.getElementById('ide-filename');
  if (fnBadge) {
    fnBadge.innerHTML = `<i class="bi bi-file-earmark-code text-warning me-1"></i>${lang === 'javascript' ? 'solution.js' : 'solution.py'}`;
  }
  resetCodeTemplate();
}

function resetCodeTemplate() {
  const langSelect = document.getElementById('mock-lang-select');
  const lang = langSelect ? langSelect.value : 'python';
  const textarea = document.getElementById('mock-user-answer');
  if (!textarea) return;

  // 1. Check if the current question has rich runnable starter code for this language
  if (currentMockQuestion?.starter_code && currentMockQuestion.starter_code[lang]) {
    textarea.value = currentMockQuestion.starter_code[lang];
    updateMockWordCount();
    return;
  }

  // 2. Fallback template
  const rawTitle = currentMockQuestion?.title || 'solution';
  const cleanTitle = rawTitle.toLowerCase().replace(/[^a-z0-9_]+/g, '_').substring(0, 30);

  if (lang === 'javascript') {
    textarea.value = `/**
 * Problem: ${currentMockQuestion?.title || 'Algorithm'}
 * Target: ${currentMockTarget}
 */

function ${cleanTitle}() {
    console.log("Testing ${cleanTitle} solution...");
    // Write your code here
    return true;
}

// Sample execution
const result = ${cleanTitle}();
console.log("Output:", result);`;
  } else {
    textarea.value = `"""
Problem: ${currentMockQuestion?.title || 'Algorithm'}
Target: ${currentMockTarget}
"""

def ${cleanTitle}():
    print("Testing ${cleanTitle} solution...")
    # Write your code here
    return True

if __name__ == "__main__":
    result = ${cleanTitle}()
    print("Output:", result)`;
  }
  updateMockWordCount();
}

// -------------------------------------------------------------
// LIVE CODE COMPILER EXECUTION
// -------------------------------------------------------------
async function runCandidateCode() {
  const code = (document.getElementById('mock-user-answer')?.value || '').trim();
  const langSelect = document.getElementById('mock-lang-select');
  const language = langSelect ? langSelect.value : 'python';
  const stdoutEl = document.getElementById('compiler-stdout');
  const statusBadge = document.getElementById('compiler-status-badge');
  const runtimeEl = document.getElementById('compiler-runtime');
  const runBtn = document.getElementById('btn-run-code');

  if (!code) {
    toast('Editor is empty. Write or paste code before running.', 'warning');
    return;
  }

  if (statusBadge) {
    statusBadge.textContent = 'Running...';
    statusBadge.className = 'badge bg-warning text-dark';
  }
  if (runBtn) {
    runBtn.disabled = true;
    runBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Compiling...';
  }

  try {
    const res = await fetch('/api/mock/run_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, language })
    });

    if (!res.ok) throw new Error('Failed to run code');
    const data = await res.json();
    const result = data.result;

    if (runtimeEl) runtimeEl.textContent = `${result.execution_time_ms} ms`;

    if (result.success) {
      if (statusBadge) {
        statusBadge.textContent = 'Exit 0 (Success)';
        statusBadge.className = 'badge bg-success';
      }
      if (stdoutEl) {
        stdoutEl.style.color = '#3fb950';
        stdoutEl.textContent = result.stdout || '[Program executed successfully with no stdout]';
      }
      toast(`Code finished in ${result.execution_time_ms}ms!`, 'success');
    } else {
      if (statusBadge) {
        statusBadge.textContent = `Exit ${result.exit_code} (Error)`;
        statusBadge.className = 'badge bg-danger';
      }
      if (stdoutEl) {
        stdoutEl.style.color = '#f85149';
        stdoutEl.textContent = (result.stderr || result.stdout || 'Execution error');
      }
      toast('Execution finished with errors.', 'danger');
    }
  } catch (err) {
    if (statusBadge) {
      statusBadge.textContent = 'Error';
      statusBadge.className = 'badge bg-danger';
    }
    if (stdoutEl) {
      stdoutEl.style.color = '#f85149';
      stdoutEl.textContent = 'Error running code: ' + err.message;
    }
    toast('Error: ' + err.message, 'danger');
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.innerHTML = '<i class="bi bi-play-fill me-1"></i> Run Code (Ctrl+Enter)';
    }
  }
}

function clearConsole() {
  const stdoutEl = document.getElementById('compiler-stdout');
  const statusBadge = document.getElementById('compiler-status-badge');
  const runtimeEl = document.getElementById('compiler-runtime');
  if (stdoutEl) {
    stdoutEl.style.color = '#58a6ff';
    stdoutEl.textContent = '$ Console cleared.';
  }
  if (statusBadge) {
    statusBadge.textContent = 'Ready';
    statusBadge.className = 'badge bg-secondary';
  }
  if (runtimeEl) runtimeEl.textContent = '0.0 ms';
}

function copyModelAnswer() {
  const modelText = document.getElementById('eval-model-answer')?.textContent || '';
  if (!modelText) return;
  navigator.clipboard.writeText(modelText)
    .then(() => toast('Exemplary model answer copied to clipboard!', 'success'))
    .catch(() => toast('Failed to copy', 'warning'));
}

// -------------------------------------------------------------
// LIVE INTERVIEW TIMER (45:00 COUNTDOWN)
// -------------------------------------------------------------
let timerSeconds = 45 * 60;
let timerInterval = null;
let timerRunning = false;

function toggleInterviewTimer() {
  const icon = document.getElementById('timer-toggle-icon');
  const text = document.getElementById('timer-toggle-text');

  if (timerRunning) {
    clearInterval(timerInterval);
    timerRunning = false;
    if (icon) icon.className = 'bi bi-play-fill';
    if (text) text.textContent = 'Resume';
    toast('Interview timer paused', 'info');
  } else {
    timerRunning = true;
    if (icon) icon.className = 'bi bi-pause-fill';
    if (text) text.textContent = 'Pause';
    toast('Interview timer started (45m)!', 'success');

    timerInterval = setInterval(() => {
      if (timerSeconds > 0) {
        timerSeconds--;
        updateTimerDisplay();
      } else {
        clearInterval(timerInterval);
        timerRunning = false;
        toast('Time is up! Submit your solution for Bar Raiser evaluation.', 'warning');
      }
    }, 1000);
  }
}

function resetInterviewTimer() {
  clearInterval(timerInterval);
  timerRunning = false;
  timerSeconds = 45 * 60;
  updateTimerDisplay();
  const icon = document.getElementById('timer-toggle-icon');
  const text = document.getElementById('timer-toggle-text');
  if (icon) icon.className = 'bi bi-play-fill';
  if (text) text.textContent = 'Start';
}

function updateTimerDisplay() {
  const timerEl = document.getElementById('interview-timer');
  if (!timerEl) return;
  const m = Math.floor(timerSeconds / 60);
  const s = timerSeconds % 60;
  timerEl.textContent = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  if (timerSeconds <= 300) {
    timerEl.classList.add('text-danger');
    timerEl.classList.remove('text-white');
  } else {
    timerEl.classList.remove('text-danger');
    timerEl.classList.add('text-white');
  }
}

function setupIDEEditor() {
  const textarea = document.getElementById('mock-user-answer');
  if (!textarea) return;

  textarea.addEventListener('keydown', function(e) {
    // Tab key inserts 4 spaces
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = this.selectionStart;
      const end = this.selectionEnd;
      this.value = this.value.substring(0, start) + '    ' + this.value.substring(end);
      this.selectionStart = this.selectionEnd = start + 4;
      updateMockWordCount();
      return;
    }

    // Ctrl+Enter or Cmd+Enter runs code
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      runCandidateCode();
      return;
    }
  });

  textarea.addEventListener('input', updateMockWordCount);
}

async function submitMockAnswer() {
  const answer = (document.getElementById('mock-user-answer')?.value || '').trim();
  if (!answer) {
    toast('Please enter your answer before submitting', 'warning');
    return;
  }
  if (!currentMockQuestion) {
    toast('No active question to evaluate', 'warning');
    return;
  }

  const btn = document.getElementById('btn-submit-mock');
  const prevBtnHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Evaluating with Bar Raiser AI...';
  }

  try {
    const res = await fetch('/api/mock/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: currentMockQuestion.question || currentMockQuestion.title,
        answer: answer,
        target: currentMockTarget
      })
    });

    if (!res.ok) throw new Error('Evaluation failed');
    const data = await res.json();
    const ev = data.evaluation;

    // Render Evaluation Card
    const evalResult = document.getElementById('mock-eval-result');
    const scoreNum = document.getElementById('eval-score-num');
    const verdictBadge = document.getElementById('eval-verdict-badge');
    const techFb = document.getElementById('eval-tech-feedback');
    const strengthsList = document.getElementById('eval-strengths-list');
    const missingList = document.getElementById('eval-missing-list');
    const modelAns = document.getElementById('eval-model-answer');

    if (scoreNum) scoreNum.textContent = ev.score || 7;
    if (verdictBadge) {
      verdictBadge.textContent = ev.verdict || 'Hire';
      verdictBadge.className = `badge bg-${ev.badge_color || 'success'} px-3 py-2 fs-6`;
    }
    if (techFb) techFb.textContent = ev.technical_depth_feedback || 'Solid conceptual understanding.';

    if (strengthsList) {
      strengthsList.innerHTML = (ev.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('');
    }
    if (missingList) {
      missingList.innerHTML = (ev.missing_concepts || []).map(m => `<li>${escapeHtml(m)}</li>`).join('');
    }
    if (modelAns) {
      modelAns.textContent = ev.model_answer || 'Complete answer covers system constraints, core patterns, and Big-O.';
    }

    if (evalResult) {
      evalResult.style.display = 'block';
      evalResult.scrollIntoView({ behavior: 'smooth' });
    }

    toast(`Evaluated! Verdict: ${ev.verdict || 'Reviewed'} (${ev.score || 7}/10)`, 'success');

  } catch (err) {
    toast('Error evaluating answer: ' + err.message, 'danger');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = prevBtnHtml;
    }
  }
}

// -------------------------------------------------------------
// EXPAND / COLLAPSE LISTS (FIRST 4, READ MORE)
// -------------------------------------------------------------
function toggleMoreCompanies() {
  const extras = document.querySelectorAll('.company-extra');
  if (extras.length === 0) return;
  const isHidden = extras[0].classList.contains('d-none');
  const toggleBtnText = document.getElementById('btn-toggle-companies-text');
  const toggleBtnIcon = document.getElementById('btn-toggle-companies-icon');
  extras.forEach(el => {
    el.classList.toggle('d-none', !isHidden);
  });
  if (isHidden) {
    if (toggleBtnText) toggleBtnText.textContent = 'Show Less';
    if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-up me-1';
  } else {
    if (toggleBtnText) toggleBtnText.textContent = `Show All Companies (${extras.length} More)`;
    if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-down me-1';
  }
}

function toggleMoreSysDesign() {
  const extras = document.querySelectorAll('.sysdesign-extra');
  if (extras.length === 0) return;
  const isHidden = extras[0].classList.contains('d-none');
  const toggleBtnText = document.getElementById('btn-toggle-sysdesign-text');
  const toggleBtnIcon = document.getElementById('btn-toggle-sysdesign-icon');
  extras.forEach(el => {
    el.classList.toggle('d-none', !isHidden);
  });
  if (isHidden) {
    if (toggleBtnText) toggleBtnText.textContent = 'Show Less';
    if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-up me-1';
  } else {
    if (toggleBtnText) toggleBtnText.textContent = `Show All System Design Cases (${extras.length} More)`;
    if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-down me-1';
  }
}

function toggleMoreModalLeetcode() {
  const extras = document.querySelectorAll('.modal-lc-extra');
  if (extras.length === 0) return;
  const isHidden = extras[0].classList.contains('d-none');
  const toggleBtnText = document.getElementById('modal-lc-toggle-text');
  const toggleBtnIcon = document.getElementById('modal-lc-toggle-icon');
  extras.forEach(el => {
    el.classList.toggle('d-none', !isHidden);
  });
  if (isHidden) {
    if (toggleBtnText) toggleBtnText.textContent = 'Show Less';
    if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-up me-1';
  } else {
    if (toggleBtnText) toggleBtnText.textContent = `Show All Problems (${extras.length} More)`;
    if (toggleBtnIcon) toggleBtnIcon.className = 'bi bi-chevron-down me-1';
  }
}

// -------------------------------------------------------------
// UTILITIES
// -------------------------------------------------------------
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function formatInline(text) {
  if (!text) return '';
  let s = escapeHtml(text);
  // Markdown links: [text](url)
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="briefing-btn-link"><i class="bi bi-box-arrow-up-right me-1"></i>$1</a>');
  // Bold
  s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Italics
  s = s.replace(/\*(.*?)\*/g, '<em>$1</em>');
  // Inline code
  s = s.replace(/`(.*?)`/g, '<code class="px-1.5 py-0.5 bg-dark text-info rounded">$1</code>');
  return s;
}

function formatMarkdown(text) {
  if (!text) return '';
  const lines = text.split(/\r?\n/);
  const html = [];

  for (let line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    // Headers (### or ## or #)
    if (trimmed.startsWith('### ')) {
      const title = formatInline(trimmed.slice(4));
      html.push(`<div class="briefing-section-heading"><i class="bi bi-chevron-right text-info me-2"></i><h4>${title}</h4></div>`);
      continue;
    }
    if (trimmed.startsWith('## ')) {
      const title = formatInline(trimmed.slice(3));
      html.push(`<div class="briefing-section-heading"><h3>${title}</h3></div>`);
      continue;
    }
    if (trimmed.startsWith('# ')) {
      const title = formatInline(trimmed.slice(2));
      html.push(`<div class="briefing-section-heading"><h2>${title}</h2></div>`);
      continue;
    }

    // Horizontal divider
    if (trimmed === '---' || trimmed === '***' || trimmed === '___') {
      html.push('<hr class="briefing-divider">');
      continue;
    }

    // Numbered list item: e.g. "1. ..."
    const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      const num = numMatch[1];
      const content = formatInline(numMatch[2]);
      html.push(`<div class="briefing-priority-card"><span class="priority-step-badge">#${num}</span><div class="priority-step-text">${content}</div></div>`);
      continue;
    }

    // Bullet item: e.g. "- ..." or "* ..."
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const content = formatInline(trimmed.slice(2));
      html.push(`<div class="briefing-bullet-item"><i class="bi bi-check-circle-fill text-success me-2 mt-1 flex-shrink-0"></i><div class="bullet-content">${content}</div></div>`);
      continue;
    }

    // Paragraph
    html.push(`<p class="briefing-paragraph mb-2">${formatInline(trimmed)}</p>`);
  }

  return html.join('');
}

// Expose all functions explicitly to window for HTML onclick compatibility
window.navigateTo = navigateTo;
window.rescoreJobs = rescoreJobs;
window.handleResumeUpload = handleResumeUpload;
window.handleDedicatedResumeUpload = handleDedicatedResumeUpload;
window.uploadResume = uploadResume;
window.switchResume = switchResume;
window.addTodo = addTodo;
window.toggleTodo = toggleTodo;
window.deleteTodo = deleteTodo;
window.clearCompletedTodos = clearCompletedTodos;
window.filterTodos = filterTodos;
window.huntJobs = huntJobs;
window.filterJobs = filterJobs;
window.resetJobFilters = resetJobFilters;
window.updateJobStatus = updateJobStatus;
window.makeDraft = makeDraft;
window.toggleHabit = toggleHabit;
window.makeBriefing = makeBriefing;
window.sendChat = sendChat;
window.quickAction = quickAction;
window.clearChat = clearChat;
window.filterPrepTracks = filterPrepTracks;
window.searchCompanyPrep = searchCompanyPrep;
window.toggleQA = toggleQA;
window.openCompanyPrep = openCompanyPrep;
window.copyCompanyIntel = copyCompanyIntel;
window.selectMockTarget = selectMockTarget;
window.randomizeMockQuestion = randomizeMockQuestion;
window.loadSystemDesignIntoMock = loadSystemDesignIntoMock;
window.startMockInterviewFromModal = startMockInterviewFromModal;
window.generateNewMockQuestion = generateNewMockQuestion;
window.updateMockWordCount = updateMockWordCount;
window.submitMockAnswer = submitMockAnswer;
window.runCandidateCode = runCandidateCode;
window.clearConsole = clearConsole;
window.handleLanguageChange = handleLanguageChange;
window.resetCodeTemplate = resetCodeTemplate;
window.toggleInterviewTimer = toggleInterviewTimer;
window.resetInterviewTimer = resetInterviewTimer;
window.copyModelAnswer = copyModelAnswer;
window.toggleMoreCompanies = toggleMoreCompanies;
window.toggleMoreSysDesign = toggleMoreSysDesign;
window.toggleMoreModalLeetcode = toggleMoreModalLeetcode;
window.loadLeetCodeProblemIntoMock = loadLeetCodeProblemIntoMock;

// Initialize on Load — RESTORE ACTIVE VIEW
document.addEventListener('DOMContentLoaded', () => {
  // Determine starting section from URL hash or localStorage (Default to 'jobs')
  const hashSec = window.location.hash.replace('#', '');
  let savedSec = null;
  try {
    savedSec = localStorage.getItem('scout_active_view');
  } catch (e) {}

  const initialView = hashSec || savedSec || 'jobs';
  navigateTo(initialView);

  updateTodoCountersFromDOM();
  setupResumeDropzone();
  setupIDEEditor();

  const searchInput = document.getElementById('job-search');
  if (searchInput) searchInput.addEventListener('input', filterJobs);

  const roleFilter = document.getElementById('job-role-filter');
  if (roleFilter) roleFilter.addEventListener('change', filterJobs);

  const locFilter = document.getElementById('job-location-filter');
  if (locFilter) locFilter.addEventListener('change', filterJobs);

  const statusFilter = document.getElementById('job-status-filter');
  if (statusFilter) statusFilter.addEventListener('change', filterJobs);

  const sourceFilter = document.getElementById('job-source-filter');
  if (sourceFilter) sourceFilter.addEventListener('change', filterJobs);

  // Apply default India & Remote filter
  filterJobs();
});

// Handle browser back/forward buttons
window.addEventListener('hashchange', () => {
  const sec = window.location.hash.replace('#', '');
  if (sec && sec !== currentSection) {
    navigateTo(sec);
  }
});
