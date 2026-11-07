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
  const activeLink = document.querySelector(`.nav-link[data-section="${section}"]`);
  if (activeLink) activeLink.classList.add('active');

  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const targetView = document.getElementById(`view-${section}`);
  if (targetView) targetView.classList.add('active');

  closeSidebar();
}

function reloadOnSection(section = 'jobs', delay = 1000) {
  window.location.hash = section;
  try {
    localStorage.setItem('scout_active_view', section);
  } catch (e) {}
  setTimeout(() => window.location.reload(), delay);
}

// Mobile sidebar
const menuToggle = document.getElementById('menu-toggle');
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebar-overlay');

if (menuToggle) {
  menuToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
  });
}

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
  toast('Drafting personalized pitch with Gemini...', 'info');
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
// UTILITIES
// -------------------------------------------------------------
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function formatMarkdown(text) {
  if (!text) return '';
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code class="px-1 bg-dark text-info rounded">$1</code>')
    .replace(/\n/g, '<br>');
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
