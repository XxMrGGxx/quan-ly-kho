// ========== NAMESPACE ==========
window.WMS = window.WMS || {};

function defineGlobalAlias(name, getter, setter) {
    const existing = Object.getOwnPropertyDescriptor(window, name);
    if (existing && !existing.configurable) {
        return;
    }
    Object.defineProperty(window, name, {
        configurable: true,
        enumerable: false,
        get: getter,
        set: setter || function(nextValue) {
            if (typeof nextValue === 'function') {
                getter._value = nextValue;
            }
        }
    });
}

// ========== DEBOUNCE ==========
window.WMS.debounce = function(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
};

// ========== TOAST ==========
window.WMS.showToast = function(msg, isError = false) {
    const existing = document.querySelector('.custom-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = 'custom-toast';
    toast.style.cssText = `
        position: fixed; top: 20px; right: 20px; 
        background: ${isError ? '#ef4444' : '#10b981'}; 
        color: white; padding: 12px 20px; border-radius: 8px; 
        z-index: 9999; animation: slideIn 0.3s ease;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); font-size: 14px;
        max-width: 350px;
    `;
    toast.innerText = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
};

// ========== FORMAT MONEY ==========
window.WMS.formatMoney = function(amount) {
    if (amount === undefined || amount === null) return '0 đ';
    return new Intl.NumberFormat('vi-VN').format(amount) + ' đ';
};

// ========== ESCAPE HTML ==========
window.WMS.escapeHtml = function(str) {
    if (str === undefined || str === null) return '';
    return String(str).replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
};

// ========== ESCAPE ATTR ==========
window.WMS.escapeAttr = function(str) {
    if (str === undefined || str === null) return '';
    return String(str).replace(/[&<>"']/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        if (m === '"') return '&quot;';
        if (m === "'") return '&#39;';
        return m;
    });
};

// ========== FORMAT HELPERS ==========
window.WMS.formatDateOnly = function(value) {
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

window.WMS.safeNumber = function(value, fallback = 0) {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
};

window.WMS.optionHtml = function(value, label, attrs = '') {
    return `<option value="${window.WMS.escapeAttr(value)}"${attrs}>${window.WMS.escapeHtml(label)}</option>`;
};

window.WMS.optionHtmlWithAttrs = function(value, label, attrs = {}) {
    const attrStr = Object.entries(attrs)
        .map(([key, val]) => ` ${key}="${window.WMS.escapeAttr(val)}"`)
        .join('');
    return `<option value="${window.WMS.escapeAttr(value)}"${attrStr}>${window.WMS.escapeHtml(label)}</option>`;
};

// ========== API ==========
window.WMS.api = async function(endpoint, method = 'GET', body = null) {
    const token = localStorage.getItem('wms_token');
    
    const headers = { 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    // Thêm CSRF token cho các method thay đổi dữ liệu (POST, PUT, DELETE)
    if (method === 'POST' || method === 'PUT' || method === 'DELETE') {
        // Đọc CSRF token từ biến global window.WMS.csrfToken (được server embed vào HTML)
        // Cookie httponly=true nên JS không đọc được trực tiếp
        let csrfToken = window.WMS && window.WMS.csrfToken;
        // Fallback: thử đọc từ cookie (dành cho trường hợp JS chưa kịp cập nhật)
        if (!csrfToken) {
            const csrfMatch = document.cookie.match(/(?:^|;\s*)wms_csrf=([^;]*)/);
            if (csrfMatch) csrfToken = csrfMatch[1];
        }
        if (csrfToken) {
            headers['X-CSRF-Token'] = csrfToken;
        }
    }
    
    try {
        const options = { 
            method, 
            headers,
            credentials: 'include'
        };
        if (body && (method === 'POST' || method === 'PUT' || method === 'DELETE')) {
            options.body = JSON.stringify(body);
        }
        
        const response = await fetch('/api' + endpoint, options);
        
        // Cập nhật CSRF token từ response header (single-use token rotation)
        const newCsrfToken = response.headers.get('X-CSRF-Token');
        if (newCsrfToken) {
            window.WMS.csrfToken = newCsrfToken;
        }
        
        if (response.status === 401) {
            localStorage.removeItem('wms_token');
            localStorage.removeItem('wms_user');
            window.location.href = '/auth';
            return null;
        }
        
        if (response.status === 403) {
            const error = await response.json().catch(() => ({}));
            window.WMS.showToast(error.detail || 'Bạn không có quyền', true);
            return null;
        }
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        if (response.status === 204) return { success: true };
        
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        window.WMS.showToast(error.message || 'Lỗi kết nối', true);
        throw error;
    }
};

// ========== LOGOUT ==========
window.WMS.logout = function() {
    localStorage.removeItem('wms_token');
    localStorage.removeItem('wms_user');
    document.cookie = 'wms_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
    window.location.href = '/auth';
};

// Alias toàn cục được bảo vệ để tránh named-property/ghi đè ngoài ý muốn.
defineGlobalAlias('debounce', () => window.WMS.debounce);
defineGlobalAlias('showToast', () => window.WMS.showToast);
defineGlobalAlias('formatMoney', () => window.WMS.formatMoney);
defineGlobalAlias('escapeHtml', () => window.WMS.escapeHtml);
defineGlobalAlias('escapeAttr', () => window.WMS.escapeAttr);
defineGlobalAlias('formatDateOnly', () => window.WMS.formatDateOnly);
defineGlobalAlias('safeNumber', () => window.WMS.safeNumber);
defineGlobalAlias('optionHtml', () => window.WMS.optionHtml);
defineGlobalAlias('optionHtmlWithAttrs', () => window.WMS.optionHtmlWithAttrs);
defineGlobalAlias('api', () => window.WMS.api);
defineGlobalAlias('logout', () => window.WMS.logout);

// ========== STYLES ==========
if (!document.getElementById('global-styles')) {
    const style = document.createElement('style');
    style.id = 'global-styles';
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #e2e8f0;
            border-top-color: #2563eb;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            vertical-align: middle;
            margin-right: 8px;
        }
        .btn-sm { padding: 4px 8px; font-size: 12px; }
        .badge { padding: 2px 8px; border-radius: 12px; font-size: 12px; display: inline-block; }
        .badge-danger { background: #fee2e2; color: #dc2626; }
        .badge-info { background: #dbeafe; color: #2563eb; }
        .badge-success { background: #dcfce7; color: #166534; }
        .badge-warning { background: #fef3c7; color: #92400e; }
    `;
    document.head.appendChild(style);
}

// ========== PRODUCT AUTOCOMPLETE ==========
/**
 * Create an autocomplete product search input.
 * The dropdown uses position:fixed so it is never clipped by overflow:hidden parents.
 * Usage: window.WMS.createProductAutocomplete(containerElement, options)
 *   - containerElement: the DOM element where the autocomplete will be placed
 *   - options.onSelect(product): callback when a product is selected
 *   - options.initialValue: product id to preselect (optional)
 *   - options.initialText: display text to preload (optional)
 *   - options.placeholder: input placeholder text (optional)
 */
window.WMS.createProductAutocomplete = function(container, options = {}) {
    const { onSelect, initialValue, placeholder } = options;

    // Build input structure inside container
    container.innerHTML = `
        <div class="product-autocomplete-wrapper">
            <input type="text" class="input product-autocomplete-input"
                placeholder="${placeholder || '🔍 Gõ tên hoặc mã sản phẩm...'}"
                autocomplete="off" spellcheck="false">
            <input type="hidden" class="product-autocomplete-id" value="${initialValue || ''}">
            <input type="hidden" class="product-autocomplete-unit" value="">
        </div>
    `;

    // Dropdown is appended to <body> to escape all overflow constraints
    const dropdown = document.createElement('div');
    dropdown.className = 'product-autocomplete-dropdown';
    document.body.appendChild(dropdown);

    const wrapper = container.querySelector('.product-autocomplete-wrapper');
    const input   = wrapper.querySelector('.product-autocomplete-input');
    const hiddenId   = wrapper.querySelector('.product-autocomplete-id');
    const hiddenUnit = wrapper.querySelector('.product-autocomplete-unit');

    let activeIndex = -1;
    let currentResults = [];
    let selectedProduct = null;
    let _lastQuery = '';

    if (options.initialText) {
        input.value = options.initialText;
    }

    // ---- Position dropdown above the input using fixed coords ----
    function positionDropdown() {
        const rect = input.getBoundingClientRect();
        const viewportH = window.innerHeight;
        const dropH = Math.min(400, dropdown.scrollHeight || 400);

        // Always show above the input field
        dropdown.style.top  = 'auto';
        dropdown.style.bottom = (viewportH - rect.top + 4) + 'px';
        dropdown.style.left  = rect.left + 'px';
        dropdown.style.maxHeight = '400px';

        // Width: at least input width, capped at 600px for better readability
        const w = Math.min(Math.max(rect.width, 360), 600);
        dropdown.style.width = w + 'px';
    }

    function openDropdown() {
        positionDropdown();
        dropdown.classList.add('active');
    }

    function closeDropdown() {
        dropdown.classList.remove('active');
        dropdown.innerHTML = '';
        activeIndex = -1;
    }

    function highlightText(text, query) {
        if (!query) return window.WMS.escapeHtml(text);
        const escaped = window.WMS.escapeHtml(text);
        const escapedQ = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return escaped.replace(new RegExp('(' + escapedQ + ')', 'gi'),
            '<span class="ac-highlight">$1</span>');
    }

    function selectProduct(product) {
        if (!product) return;
        input.value = (product.code || '') + ' - ' + (product.name || '');
        hiddenId.value   = product.id;
        hiddenUnit.value = product.unit_name || '';
        selectedProduct  = product;
        closeDropdown();
        if (typeof onSelect === 'function') onSelect(product);
    }

    function renderResults(results, query) {
        dropdown.innerHTML = '';
        currentResults = results;
        activeIndex = -1;

        if (!results || results.length === 0) {
            dropdown.innerHTML = '<div class="ac-empty">Không tìm thấy sản phẩm</div>';
            openDropdown();
            return;
        }

        // Header
        const header = document.createElement('div');
        header.className = 'ac-header';
        header.innerHTML = '<span>Tên sản phẩm</span><span>Mã SP</span><span style="text-align:right">Tồn kho</span>';
        dropdown.appendChild(header);

        results.forEach((product, idx) => {
            const item = document.createElement('div');
            item.className = 'ac-item';
            item.dataset.index = idx;
            const stock = window.WMS.safeNumber(product.stock, 0);
            const stockColor = stock <= 0 ? 'color:#ef4444;background:#fef2f2;' : '';
            item.innerHTML = `
                <span class="ac-name" title="${window.WMS.escapeAttr(product.name)}">${highlightText(product.name, query)}</span>
                <span class="ac-code">${highlightText(product.code || '', query)}</span>
                <span class="ac-stock" style="${stockColor}">${new Intl.NumberFormat('vi-VN').format(stock)}</span>
            `;
            item.addEventListener('mousedown', (e) => {
                // mousedown fires before blur; prevent blur from closing dropdown first
                e.preventDefault();
                selectProduct(product);
            });
            item.addEventListener('mouseenter', () => {
                activeIndex = idx;
                dropdown.querySelectorAll('.ac-item').forEach(el => el.classList.remove('active'));
                item.classList.add('active');
            });
            dropdown.appendChild(item);
        });

        openDropdown();
    }

    // Debounced search
    const doSearch = window.WMS.debounce(async function(query) {
        if (!query || query.trim().length < 1) { closeDropdown(); return; }
        _lastQuery = query.trim();
        // Show loading state
        dropdown.innerHTML = '<div class="ac-loading">⏳ Đang tìm kiếm...</div>';
        openDropdown();
        try {
            const data = await window.WMS.api('/products?search=' + encodeURIComponent(_lastQuery) + '&limit=20');
            const items = data?.items || [];
            renderResults(items, _lastQuery);
        } catch (e) {
            closeDropdown();
        }
    }, 250);

    input.addEventListener('input', function() {
        const val = this.value.trim();
        if (val === '') {
            hiddenId.value = '';
            hiddenUnit.value = '';
            selectedProduct = null;
            closeDropdown();
        } else {
            doSearch(val);
        }
    });

    input.addEventListener('focus', function() {
        if (currentResults.length > 0) {
            openDropdown();
        } else if (this.value.trim().length > 0) {
            doSearch(this.value.trim());
        }
    });

    input.addEventListener('blur', function() {
        // Small delay so mousedown on item fires first
        setTimeout(() => closeDropdown(), 150);
    });

    // Reposition on scroll/resize
    const reposition = window.WMS.debounce(() => {
        if (dropdown.classList.contains('active')) positionDropdown();
    }, 50);
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);

    // Keyboard navigation
    input.addEventListener('keydown', function(e) {
        const items = dropdown.querySelectorAll('.ac-item');
        if (!dropdown.classList.contains('active') || items.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = Math.min(activeIndex + 1, items.length - 1);
            items.forEach(el => el.classList.remove('active'));
            items[activeIndex].classList.add('active');
            items[activeIndex].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = Math.max(activeIndex - 1, 0);
            items.forEach(el => el.classList.remove('active'));
            items[activeIndex].classList.add('active');
            items[activeIndex].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (activeIndex >= 0 && activeIndex < currentResults.length) {
                selectProduct(currentResults[activeIndex]);
            }
        } else if (e.key === 'Escape') {
            closeDropdown();
        }
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!wrapper.contains(e.target) && !dropdown.contains(e.target)) {
            closeDropdown();
        }
    });

    // Cleanup: remove dropdown from body when container is removed
    const observer = new MutationObserver(() => {
        if (!document.body.contains(container)) {
            dropdown.remove();
            observer.disconnect();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    return {
        getValue:  () => parseInt(hiddenId.value) || 0,
        getUnit:   () => hiddenUnit.value,
        getProduct:() => selectedProduct,
        setValue:  (product) => selectProduct(product),
        clear: () => {
            input.value = '';
            hiddenId.value = '';
            hiddenUnit.value = '';
            selectedProduct = null;
            closeDropdown();
        },
        input,
        hiddenId,
        hiddenUnit
    };
};

console.log('✅ app.js loaded - api:', typeof window.WMS.api);
