
// Bootstrap sớm để template script trong content có thể dùng ngay.
window.WMS = window.WMS || {};
window.WMS.escapeHtml = window.WMS.escapeHtml || function(str) {
    if (str === undefined || str === null) return '';
    return String(str).replace(/[&<>]/g, function(m) {
        if (m === '&') return '&';
        if (m === '<') return '<';
        if (m === '>') return '>';
        return m;
    });
};
window.WMS.escapeAttr = window.WMS.escapeAttr || function(str) {
    if (str === undefined || str === null) return '';
    return String(str).replace(/[&<>"']/g, function(m) {
        if (m === '&') return '&';
        if (m === '<') return '<';
        if (m === '>') return '>';
        if (m === '"') return '"';
        if (m === "'") return '&#39;';
        return m;
    });
};
window.WMS.safeNumber = window.WMS.safeNumber || function(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
};
window.WMS.formatCurrency = window.WMS.formatCurrency || function(amount) {
    const num = window.WMS.safeNumber(amount, 0);
    return new Intl.NumberFormat('vi-VN', {
        style: 'currency',
        currency: 'VND',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(num);
};
window.WMS.formatMoney = window.WMS.formatMoney || window.WMS.formatCurrency;
window.WMS.formatDateOnly = window.WMS.formatDateOnly || function(value) {
    if (!value) return '-';
    const str = String(value);
    // Chuyển định dạng từ yyyy-MM-dd sang dd/MM/yyyy (Việt Nam)
    const datePart = str.includes('T') ? str.split('T')[0] : str;
    if (datePart.match(/^\d{4}-\d{2}-\d{2}$/)) {
        const [y, m, d] = datePart.split('-');
        return `${d}/${m}/${y}`;
    }
    return str;
};
window.WMS.optionHtml = window.WMS.optionHtml || function(value, label, attrs = '') {
    return `<option value="${window.WMS.escapeAttr(value)}"${attrs}>${window.WMS.escapeHtml(label)}</option>`;
};
window.WMS.optionHtmlWithAttrs = window.WMS.optionHtmlWithAttrs || function(value, label, attrs = {}) {
    const attrStr = Object.entries(attrs)
        .map(([key, val]) => ` ${key}="${window.WMS.escapeAttr(val)}"`)
        .join('');
    return `<option value="${window.WMS.escapeAttr(value)}"${attrStr}>${window.WMS.escapeHtml(label)}</option>`;
};
window.WMS.showToast = window.WMS.showToast || function(msg) { alert(msg); };

// ========== TOAST NOTIFICATION SYSTEM ==========
(function() {
    const TOAST_ICONS = {
        success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
        error: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`
    };

    const TOAST_TITLES = {
        success: 'Thành công',
        error: 'Lỗi',
        warning: 'Cảnh báo',
        info: 'Thông tin'
    };

    let toastContainer = null;
    let toastQueue = [];
    let toastIdCounter = 0;

    function getContainer() {
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container';
            toastContainer.setAttribute('aria-live', 'polite');
            toastContainer.setAttribute('aria-atomic', 'true');
            document.body.appendChild(toastContainer);
        }
        return toastContainer;
    }

    function createToastElement(type, title, message, duration) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.setAttribute('role', 'alert');
        
        const iconHtml = TOAST_ICONS[type] || TOAST_ICONS.info;
        const durationText = duration > 0 ? `${Math.ceil(duration / 1000)}s` : '';
        
        toast.innerHTML = `
            <div class="toast-icon">${iconHtml}</div>
            <div class="toast-content">
                <div class="toast-title">${window.WMS.escapeHtml(title)}</div>
                ${message ? `<div class="toast-message">${window.WMS.escapeHtml(message)}</div>` : ''}
            </div>
            <button class="toast-close" aria-label="Đóng">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
            </button>
            <div class="toast-progress"></div>
        `;

        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => removeToast(toast));

        return toast;
    }

    function startProgress(toast, duration) {
        if (duration <= 0) return;
        const progress = toast.querySelector('.toast-progress');
        if (!progress) return;
        
        progress.style.transition = `width ${duration}ms linear`;
        requestAnimationFrame(() => {
            progress.style.width = '0%';
        });
    }

    function showToast(type, title, message, duration = 5000) {
        const container = getContainer();
        const toast = createToastElement(type, title, message, duration);
        const toastId = ++toastIdCounter;
        toast.dataset.toastId = toastId;

        container.appendChild(toast);
        toastQueue.push({ toast, toastId, timeout: null });

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                toast.classList.add('show');
            });
        });

        startProgress(toast, duration);

        if (duration > 0) {
            const timeout = setTimeout(() => {
                removeToast(toast);
            }, duration);
            toast.dataset.timeout = timeout;
        }

        // Limit to 4 visible toasts
        while (container.children.length > 4) {
            removeToast(container.firstElementChild);
        }

        return toast;
    }

    function removeToast(toast) {
        if (!toast || !toast.parentNode) return;
        
        toast.classList.remove('show');
        toast.classList.add('hide');
        
        const timeout = toast.dataset.timeout;
        if (timeout) {
            clearTimeout(parseInt(timeout));
        }

        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            toastQueue = toastQueue.filter(item => item.toast !== toast);
        }, 400);
    }

    // Public API
    window.WMS.toast = {
        success: (title, message, duration) => showToast('success', title, message, duration),
        error: (title, message, duration) => showToast('error', title, message, duration),
        warning: (title, message, duration) => showToast('warning', title, message, duration),
        info: (title, message, duration) => showToast('info', title, message, duration),
        dismissAll: () => {
            toastQueue.forEach(item => removeToast(item.toast));
            toastQueue = [];
        }
    };

    // Update legacy showToast to use new system
    const originalShowToast = window.WMS.showToast;
    window.WMS.showToast = function(msg, isError = false) {
        if (typeof msg === 'string' && !isError) {
            return window.WMS.toast.info('Thông báo', msg, 4000);
        }
        if (typeof msg === 'string' && isError) {
            return window.WMS.toast.error('Lỗi', msg, 6000);
        }
        return originalShowToast(msg);
    };
})();

window.WMS.logout = window.WMS.logout || function() {
    localStorage.removeItem('wms_token');
    localStorage.removeItem('wms_user');
    document.cookie = 'wms_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    window.location.href = '/auth';
};


// ========== KIỂM TRA BẢN QUYỀN - FOOTER SIDEBAR + BANNER ==========
async function checkLicenseStatus() {
    // Không kiểm tra nếu chưa đăng nhập (không có token)
    const token = localStorage.getItem('wms_token');
    if (!token) return;

    // Chỉ kiểm tra license nếu là admin
    try {
        const userStr = localStorage.getItem('wms_user');
        if (userStr) {
            const user = JSON.parse(userStr);
            if (user.role !== 'admin') return;
        }
    } catch(e) { return; }
    
    try {
        const resp = await fetch('/api/license/check');
        const data = await resp.json();
        const status = data.status || 'none';
        
        const indicator = document.getElementById('license-indicator');
        const footerText = document.getElementById('license-footer-text');
        const footerLink = document.getElementById('license-footer-link');
        
        if (status === 'active') {
            indicator.className = 'license-footer-indicator active';
            footerText.textContent = 'Bản quyền chính thức';
        } else if (status === 'trial') {
            indicator.className = 'license-footer-indicator trial';
            const days = data.info?.days_left || 0;
            footerText.textContent = `Dùng thử (${days} ngày)`;
        } else if (status === 'trial_expired') {
            indicator.className = 'license-footer-indicator expired';
            footerText.textContent = 'Hết hạn dùng thử';
        } else if (status === 'expired') {
            indicator.className = 'license-footer-indicator expired';
            footerText.textContent = 'Bản quyền đã hết hạn';
        } else {
            indicator.className = 'license-footer-indicator expired';
            footerText.textContent = 'Chưa kích hoạt';
        }

        try {
            const profileResp = await fetch('/api/license/company-profile');
            const profileData = await profileResp.json();
            window.WMS = window.WMS || {};
            window.WMS.companyProfile = profileData.profile || {};

            const profile = window.WMS.companyProfile;
            const brandTitle = document.querySelector('.brand-title');
            const brandSubtitle = document.querySelector('.brand-subtitle');
            if (brandTitle) brandTitle.textContent = profile.short_name || profile.company_name || 'An Tín WMS';
            if (brandSubtitle) brandSubtitle.textContent = profile.company_name || 'Warehouse Management';

            const footerText = document.getElementById('license-footer-text');
            if (footerText && profile.company_name) {
                const baseStatus = footerText.dataset.baseStatus || footerText.textContent;
                footerText.dataset.baseStatus = baseStatus;
                footerText.textContent = `${baseStatus} • ${profile.company_name}`;
            }
        } catch (profileError) {
            console.warn('Company profile load error:', profileError);
        }
        
        if (window.location.pathname !== '/license') {
            const restrictionsResp = await fetch('/api/license/restrictions');
            const restr = await restrictionsResp.json();
            
            const warningBanner = document.getElementById('license-warning-banner');
            const expiredBanner = document.getElementById('license-expired-banner');
            
            if (restr.show_warning && warningBanner) {
                document.getElementById('license-warning-text').textContent = restr.warning_message || '';
                warningBanner.style.display = 'block';
                if (expiredBanner) expiredBanner.style.display = 'none';
            } else {
                if (warningBanner) warningBanner.style.display = 'none';
                if (expiredBanner) expiredBanner.style.display = 'none';
            }
        }
    } catch(e) {
        console.error('License check error:', e);
        const footerText = document.getElementById('license-footer-text');
        if (footerText) footerText.textContent = 'Không thể kiểm tra';
    }
}

document.addEventListener('DOMContentLoaded', checkLicenseStatus);
setInterval(checkLicenseStatus, 5 * 60 * 1000);



// ========== HIỂN THỊ IP LOCAL ==========
document.addEventListener('DOMContentLoaded', function() {
    const ipEl = document.getElementById('brand-ip');
    if (!ipEl) return;
    fetch('/api/system/ip')
        .then(r => r.json())
        .then(data => {
            if (data && data.ip) ipEl.textContent = `🌐 ${data.ip}`;
        })
        .catch(() => {});
});

// ========== HIỂN THỊ / ẨN MỤC CÀI ĐẶT & BẢN QUYỀN (Chỉ admin) ==========
document.addEventListener('DOMContentLoaded', function() {
    const userStr = localStorage.getItem('wms_user');
    let isAdmin = false;
    if (userStr) {
        try {
            const user = JSON.parse(userStr);
            isAdmin = (user.role === 'admin');
        } catch (e) {}
    }
    
    // Settings nav item
    const navSettings = document.getElementById('nav-settings');
    if (navSettings) {
        navSettings.style.display = isAdmin ? '' : 'none';
    }
    
    // License footer link & indicator - chỉ admin mới thấy
    const licenseFooter = document.getElementById('license-footer');
    if (licenseFooter) {
        licenseFooter.style.display = isAdmin ? 'flex' : 'none';
    }
    
    // License warning/expired banners - chỉ admin mới thấy
    const warningBanner = document.getElementById('license-warning-banner');
    if (warningBanner) {
        warningBanner.style.display = 'none';
    }
    const expiredBanner = document.getElementById('license-expired-banner');
    if (expiredBanner) {
        expiredBanner.style.display = 'none';
    }
});

// ========== SIDEBAR HIDE/SHOW TOGGLE ==========
function toggleSidebarCollapse() {
    const sidebar = document.getElementById('sidebar');
    const showBtn = document.getElementById('sidebar-show-btn');
    const isHidden = sidebar.classList.toggle('sidebar-hidden');
    // Show/hide the show button
    if (showBtn) {
        showBtn.style.display = isHidden ? 'inline-flex' : 'none';
    }
    // Lưu trạng thái vào localStorage
    localStorage.setItem('wms_sidebar_hidden', isHidden ? '1' : '0');
}

// Khôi phục trạng thái sidebar từ localStorage
(function() {
    const sidebar = document.getElementById('sidebar');
    const showBtn = document.getElementById('sidebar-show-btn');
    if (sidebar && localStorage.getItem('wms_sidebar_hidden') === '1') {
        sidebar.classList.add('sidebar-hidden');
        if (showBtn) showBtn.style.display = 'inline-flex';
    }
})();

// ========== SIDEBAR TOGGLE (Mobile) ==========
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const body = document.body;
    const isOpen = sidebar.classList.contains('open');
    
    if (isOpen) {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
        body.classList.remove('sidebar-open');
    } else {
        sidebar.classList.add('open');
        overlay.classList.add('active');
        body.classList.add('sidebar-open');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.nav-item').forEach(link => {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 768) toggleSidebar();
        });
    });
});

// ========== ACTIVE PAGE HIGHLIGHT & USER INFO ==========
document.addEventListener('DOMContentLoaded', function() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-item').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath) {
            link.classList.add('active');
        } else if ((currentPath === '/' || currentPath === '/index') && href === '/index') {
            link.classList.add('active');
        }
    });
    
    const userStr = localStorage.getItem('wms_user');
    if (userStr) {
        try {
            const user = JSON.parse(userStr);
            const headerUserName = document.getElementById('header-user-name');
            const headerUserRole = document.getElementById('header-user-role');
            const headerAvatar = document.getElementById('header-avatar');
            const displayName = user.full_name || user.username || 'User';
            if (headerUserName) headerUserName.innerText = displayName;
            if (headerUserRole) headerUserRole.innerText = user.role || 'System operator';
            if (headerAvatar) headerAvatar.innerText = (displayName || 'U').trim().charAt(0).toUpperCase();

            if (user.role === 'saler') {
                const brandLink = document.querySelector('.brand');
                if (brandLink) brandLink.setAttribute('href', '/sales-entry');

                const allowedPaths = ['/sales-entry', '/customers'];
                document.querySelectorAll('.nav-section').forEach(section => {
                    const hasAllowed = section.querySelector('a[href]') && 
                        Array.from(section.querySelectorAll('a[href]')).some(a => 
                            allowedPaths.includes(a.getAttribute('href'))
                        );
                    if (!hasAllowed) {
                        section.style.display = 'none';
                    } else {
                        section.querySelectorAll('.nav-item').forEach(item => {
                            if (!allowedPaths.includes(item.getAttribute('href'))) {
                                item.style.display = 'none';
                            }
                        });
                    }
                });
            }
        } catch(e) {
            console.error('Parse user error:', e);
        }
    }
    
    const pageTitleMap = {
        '/index': 'Dashboard', '/products': 'Hàng hóa', '/customers': 'Khách hàng',
        '/suppliers': 'Nhà cung cấp', '/export': 'Xuất kho', '/import': 'Nhập kho', 
        '/inventory': 'Tồn kho', '/sales-entry': 'Bán hàng', '/warehouses': 'Kho bãi',
        '/reports': 'Báo cáo', '/users': 'Người dùng', '/license': 'Bản quyền',
        '/debt': 'Công nợ'
    };
    const titleEl = document.getElementById('page-title');
    if (titleEl && pageTitleMap[currentPath]) titleEl.innerText = pageTitleMap[currentPath];
});
