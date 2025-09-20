// Auth logic for login, localStorage, and logout
if (window.location.pathname === '/login') {
  if (localStorage.getItem('jwt_token')) {
    window.location.replace('/');
  }
  document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    const box = document.getElementById('msg');
    box.style.display = 'none';
    try {
      const res = await fetch('/custom-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (!res.ok) {
        box.textContent = data.error || data.detail || 'Login failed';
        box.className = 'msg error';
        box.style.display = 'block';
        return;
      }
      // Store JWT token and student details
      localStorage.setItem('jwt_token', data.access_token);
      localStorage.setItem('student_details', JSON.stringify(data.student));
      localStorage.setItem('user_role', data.role);
      
      box.textContent = 'Welcome ' + data.student.first_name + ' ' + data.student.last_name + '. Redirecting...';
      box.className = 'msg success';
      box.style.display = 'block';
      setTimeout(() => window.location.replace('/'), 600);
    } catch (err) {
      box.textContent = 'Network error';
      box.className = 'msg error';
      box.style.display = 'block';
    }
  });
}

// Logout logic for any page
if (document.getElementById('logoutBtn')) {
  document.getElementById('logoutBtn').addEventListener('click', function() {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('student_details');
    localStorage.removeItem('user_role');
    window.location.replace('/login');
  });
}

// Protect list page
if (window.location.pathname === '/' && !localStorage.getItem('jwt_token')) {
  window.location.replace('/login');
}

// Utility function to get authorization headers for API calls
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

// Utility function to make authenticated API calls
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
  
  // If token is invalid, redirect to login
  if (response.status === 401) {
    localStorage.removeItem('jwt_token');
    localStorage.removeItem('student_details');
    localStorage.removeItem('user_role');
    window.location.replace('/login');
    return null;
  }
  
  return response;
}

// Student login (ID + password) with intent redirect
if (window.location.pathname === '/student-login') {
  const form = document.getElementById('studentLoginForm');
  const msg = document.getElementById('studentMsg');

  // Prefill pending id if present
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
      localStorage.setItem('student_id', data.student_id);
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
