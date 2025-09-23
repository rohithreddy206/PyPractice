// Auth logic for login, localStorage, and logout
if (window.location.pathname === '/login') {
  // Admin login handler (adds token so admin actions work)
  const form = document.getElementById('adminLoginForm');
  const msg = document.getElementById('adminMsg');
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    msg && (msg.style.display = 'none');
    const username = document.getElementById('admin_username')?.value.trim();
    const password = document.getElementById('admin_password')?.value.trim();
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (!res.ok) {
        if (msg) {
            msg.textContent = data.detail || 'Login failed';
            msg.className = 'msg error';
            msg.style.display = 'block';
        }
        return;
      }
      localStorage.setItem('jwt_token', data.access_token);
      localStorage.setItem('user_role', data.role);
      if (data.student_id !== undefined) {
        localStorage.setItem('student_id', data.student_id);
      }
      if (msg) {
        msg.textContent = 'Login successful. Redirecting...';
        msg.className = 'msg success';
        msg.style.display = 'block';
      }
      setTimeout(()=>window.location.replace('/'), 400);
    } catch {
      if (msg) {
        msg.textContent = 'Network error';
        msg.className = 'msg error';
        msg.style.display = 'block';
      }
    }
  });
}

// Logout logic for any page
if (document.getElementById('logoutBtn')) {
  document.getElementById('logoutBtn').addEventListener('click', function() {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('student_details');
    localStorage.removeItem('user_role');
    localStorage.removeItem('student_id');
    window.location.replace('/login');
  });
}

// Root page logic: allow open access for registration if no token
if (window.location.pathname === '/') {
  const token = localStorage.getItem('jwt_token');
  const role = localStorage.getItem('user_role');
  if (token && role && role !== 'admin') {
    const sid = localStorage.getItem('student_id');
    if (sid) window.location.replace(`/students/${sid}`);
  }
}

function getAuthHeaders() {
  const token = localStorage.getItem('jwt_token');
  if (!token) {
    window.location.replace('/login');
    return {};
  }
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
}

async function authenticatedFetch(url, options = {}) {
  const authHeaders = getAuthHeaders();
  const finalOptions = {
    ...options,
    headers: {
      ...authHeaders,
      ...(options.headers || {})
    }
  };
  const response = await fetch(url, finalOptions);
  if (response.status === 401) {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('student_details');
    localStorage.removeItem('user_role');
    window.location.replace('/login');
    return null;
  }
  return response;
}

const LOGIN_MAX_ATTEMPTS = 3;

function startLockCountdown(lockKey, seconds, msgEl, submitBtn) {
  const until = Date.now() + seconds * 1000;
  localStorage.setItem(lockKey, until);
  if (submitBtn) submitBtn.disabled = true;
  function tick() {
    const remain = until - Date.now();
    if (remain <= 0) {
      localStorage.removeItem(lockKey);
      if (submitBtn) submitBtn.disabled = false;
      if (msgEl) {
        msgEl.textContent = 'You can try again.';
        msgEl.className = 'msg success';
        msgEl.style.display = 'block';
      }
      return;
    }
    const s = Math.ceil(remain / 1000);
    if (msgEl) {
      msgEl.textContent = `Too many failed attempts. Wait ${s}s`;
      msgEl.className = 'msg error';
      msgEl.style.display = 'block';
    }
    setTimeout(tick, 1000);
  }
  tick();
}

function restoreLock(lockKey, msgEl, submitBtn) {
  const untilStr = localStorage.getItem(lockKey);
  if (!untilStr) return;
  const until = parseInt(untilStr, 10);
  if (isNaN(until) || until <= Date.now()) {
    localStorage.removeItem(lockKey);
    return;
  }
  const remain = Math.ceil((until - Date.now()) / 1000);
  startLockCountdown(lockKey, remain, msgEl, submitBtn);
}

if (window.location.pathname === '/student-login') {
  const form = document.getElementById('studentLoginForm');
  const msg = document.getElementById('studentMsg');
  const submitBtn = form?.querySelector('button[type=submit]');
  const LOCK_KEY = 'student_login_lock';
  const pendingId = localStorage.getItem('pending_student_id');
  if (pendingId && document.getElementById('student_id')) {
    document.getElementById('student_id').value = pendingId;
  }
  restoreLock(LOCK_KEY, msg, submitBtn);

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (submitBtn?.disabled) return;
    msg.style.display = 'none';
    const sid = document.getElementById('student_id').value.trim();
    const password = document.getElementById('student_password').value.trim();
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ student_id: parseInt(sid,10), password })
      });
      const data = await res.json().catch(()=>({}));
      if (!res.ok) {
        if (data.locked) {
          startLockCountdown(LOCK_KEY, data.retry_after_seconds || 60, msg, submitBtn);
        } else {
            const used = data.attempts_used ?? 0;
            const left = data.attempts_remaining ?? (LOGIN_MAX_ATTEMPTS - used);
            msg.textContent = (data.detail || 'Login failed') +
              ` (${used}/${LOGIN_MAX_ATTEMPTS} used, ${left} left)`;
            msg.className = 'msg error';
            msg.style.display = 'block';
        }
        return;
      }
      localStorage.removeItem(LOCK_KEY);
      localStorage.setItem('jwt_token', data.access_token);
      if (data.role !== 'admin') localStorage.setItem('student_id', data.student_id);
      localStorage.setItem('user_role', data.role);
      msg.textContent = 'Login successful. Redirecting...';
      msg.className = 'msg success';
      msg.style.display = 'block';
      const target = localStorage.getItem('after_login_target');
      const targetId = localStorage.getItem('pending_student_id');
      setTimeout(() => {
        localStorage.removeItem('after_login_target');
        localStorage.removeItem('pending_student_id');
        if (target && targetId && parseInt(targetId,10) === data.student_id) {
          window.location.replace(
            target === 'subjects'
              ? `/students/${data.student_id}/subjects`
              : `/students/${data.student_id}`
          );
        } else {
          window.location.replace(`/students/${data.student_id}`);
        }
      }, 500);
    } catch {
      msg.textContent = 'Network error';
      msg.className = 'msg error';
      msg.style.display = 'block';
    }
  });
}
