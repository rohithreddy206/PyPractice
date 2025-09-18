// Auth logic for login, localStorage, and logout
if (window.location.pathname === '/login') {
  if (localStorage.getItem('SECURITY_TOKEN')) {
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
        box.textContent = data.detail || 'Login failed';
        box.className = 'msg error';
        box.style.display = 'block';
        return;
      }
      localStorage.setItem('SECURITY_TOKEN', data.token);
      localStorage.setItem('LOGGED_IN_USER', data.username || username);
      box.textContent = 'Welcome ' + (data.username || username) + '. Redirecting...';
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
    localStorage.removeItem('SECURITY_TOKEN');
    localStorage.removeItem('LOGGED_IN_USER');
    window.location.replace('/login');
  });
}

// Protect list page
if (window.location.pathname === '/' && !localStorage.getItem('SECURITY_TOKEN')) {
  window.location.replace('/login');
}
