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

if (window.location.pathname === '/student-login') {
  const form = document.getElementById('studentLoginForm');
  const msg = document.getElementById('studentMsg');
  const pendingId = localStorage.getItem('pending_student_id');
  if (pendingId && document.getElementById('student_id')) {
    document.getElementById('student_id').value = pendingId;
  }
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    msg.style.display = 'none';
    const sid = document.getElementById('student_id').value.trim();
    const password = document.getElementById('student_password').value.trim();
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ student_id: parseInt(sid,10), password })
      });
      const data = await res.json();
      if (!res.ok) {
        msg.textContent = data.detail || 'Login failed';
        msg.className = 'msg error';
        msg.style.display = 'block';
        return;
      }
      localStorage.setItem('jwt_token', data.access_token);
      if (data.role !== 'admin') {
        localStorage.setItem('student_id', data.student_id);
      }
      localStorage.setItem('user_role', data.role);
      const target = localStorage.getItem('after_login_target');
      const targetId = localStorage.getItem('pending_student_id');
      msg.textContent = 'Login successful. Redirecting...';
      msg.className = 'msg success';
      msg.style.display = 'block';
      setTimeout(() => {
        localStorage.removeItem('after_login_target');
        localStorage.removeItem('pending_student_id');
        if (target && targetId && parseInt(targetId,10) === data.student_id) {
            if (target === 'subjects') {
              window.location.replace(`/students/${data.student_id}/subjects`);
            } else {
              window.location.replace(`/students/${data.student_id}`);
            }
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
