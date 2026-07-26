// Clear old data on page load
localStorage.removeItem('wms_token');
localStorage.removeItem('wms_user');
document.cookie = 'wms_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';

const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const msg = document.getElementById('msg');
        const btn = document.querySelector('.btn');
        
        if (!username || !password) {
            msg.innerText = 'Vui lòng nhập đầy đủ thông tin';
            return;
        }
        
        btn.innerText = 'Đang xử lý...';
        btn.disabled = true;
        msg.innerText = '';

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                credentials: 'include',  // Quan trọng: nhận cookie
                body: JSON.stringify({ username: username, password: password })
            });
            
            const data = await response.json();
            
            if (response.ok && data.token) {
                // Lưu token vào localStorage
                localStorage.setItem('wms_token', data.token);
                localStorage.setItem('wms_user', JSON.stringify(data.user));
                
                // Cookie đã được set từ server
                msg.style.background = '#dcfce7';
                msg.style.color = '#166534';
                msg.innerText = 'Đăng nhập thành công! Đang chuyển hướng...';
                
                setTimeout(() => {
                    window.location.href = '/index';
                }, 1000);
            } else {
                msg.style.background = '#fef2f2';
                msg.style.color = '#ef4444';
                msg.innerText = data.detail || 'Sai tên đăng nhập hoặc mật khẩu';
                btn.innerText = 'Đăng nhập';
                btn.disabled = false;
            }
        } catch (err) {
            console.error('Login error:', err);
            msg.style.background = '#fef2f2';
            msg.style.color = '#ef4444';
            msg.innerText = 'Không thể kết nối đến máy chủ';
            btn.innerText = 'Đăng nhập';
            btn.disabled = false;
        }
    });

    // Auto fill demo accounts (for testing only)
    const urlParams = new URLSearchParams(window.location.search);
    const demo = urlParams.get('demo');
    if (demo === 'admin') {
        document.getElementById('username').value = 'admin';
        document.getElementById('password').value = 'admin123';
    } else if (demo === 'manager') {
        document.getElementById('username').value = 'manager1';
        document.getElementById('password').value = 'manager123';
    } else if (demo === 'staff') {
        document.getElementById('username').value = 'staff1';
        document.getElementById('password').value = 'staff123';
    } else if (demo === 'saler') {
        document.getElementById('username').value = 'saler1';
        document.getElementById('password').value = 'saler123';
    }
}