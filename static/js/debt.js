

let currentDebtTab = 'all';
let rawCustomers = [];
let rawSuppliers = [];
let rawPayments = [];

function switchDebtTab(tab) {
    currentDebtTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    
    const debtTable = document.getElementById('table-debt');
    const paymentsTable = document.getElementById('table-payments');
    
    if (tab === 'payments') {
        debtTable.style.display = 'none';
        paymentsTable.style.display = 'table';
        loadPayments();
    } else {
        paymentsTable.style.display = 'none';
        debtTable.style.display = 'table';
    }
    
    updateFilterOptions();
    filterDebt();
}

function updateFilterOptions() {
    const statusSelect = document.getElementById('debt-status');
    const statusLabel = document.getElementById('debt-status-label');
    const searchInput = document.getElementById('debt-search');
    statusSelect.innerHTML = '';
    
    if (currentDebtTab === 'payments') {
        statusLabel.innerText = 'Loại';
        searchInput.placeholder = 'Đối tác, đơn hàng, ghi chú...';
        statusSelect.innerHTML += `<option value="">Tất cả</option>`;
        statusSelect.innerHTML += `<option value="customer">Khách hàng</option>`;
        statusSelect.innerHTML += `<option value="supplier">Nhà cung cấp</option>`;
    } else {
        statusLabel.innerText = 'Trạng thái';
        searchInput.placeholder = 'Mã, tên...';
        statusSelect.innerHTML += `<option value="">Tất cả</option>`;
        statusSelect.innerHTML += `<option value="over_limit">Vượt hạn mức</option>`;
        statusSelect.innerHTML += `<option value="has_debt">Có nợ</option>`;
        statusSelect.innerHTML += `<option value="normal">Bình thường</option>`;
    }
}

function resetFilters() {
    document.getElementById('debt-search').value = '';
    document.getElementById('debt-status').value = '';
    filterDebt();
}

function fmtMoney(amount) {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount || 0);
}

function getFilteredPartners() {
    const keyword = document.getElementById('debt-search').value.toLowerCase().trim();
    const status = document.getElementById('debt-status').value;
    let result = [];
    
    // Luôn gộp khách hàng và nhà cung cấp
    result = [
        ...rawCustomers.map(c => ({ ...c, partner_type: 'customer' })),
        ...rawSuppliers.map(s => ({ ...s, partner_type: 'supplier' }))
    ];
    
    return result.filter(item => {
        const name = item.name || '';
        const code = item.code || '';
        const matchKeyword = !keyword || 
            code.toLowerCase().includes(keyword) ||
            name.toLowerCase().includes(keyword);
            
        let matchStatus = true;
        const isOver = item.is_over_limit;
        const hasDebt = item.current_debt > 0;
        
        if (status === 'over_limit') matchStatus = isOver;
        else if (status === 'has_debt') matchStatus = hasDebt;
        else if (status === 'normal') matchStatus = !hasDebt && !isOver;
        
        return matchKeyword && matchStatus;
    });
}

function getFilteredPayments() {
    const keyword = document.getElementById('debt-search').value.toLowerCase().trim();
    const type = document.getElementById('debt-status').value;
    
    return rawPayments.filter(p => {
        const matchKeyword = !keyword || 
            (p.partner_name && p.partner_name.toLowerCase().includes(keyword)) ||
            (p.order_code && p.order_code.toLowerCase().includes(keyword)) ||
            (p.notes && p.notes.toLowerCase().includes(keyword));
            
        const matchType = !type || p.partner_type === type;
        
        return matchKeyword && matchType;
    });
}

function renderMergedTable(data) {
    const body = document.getElementById('debt-merged-body');
    body.innerHTML = '';
    if (data && data.length > 0) {
        data.forEach(item => {
            const isOver = item.is_over_limit;
            const hasDebt = item.current_debt > 0;
            
            // Xác định class cho màu nền dòng
            let rowClass = 'debt-row-normal';
            if (isOver) rowClass = 'debt-row-over-limit';
            else if (hasDebt) rowClass = 'debt-row-warning';
            
            const typeLabel = item.partner_type === 'customer' ? 'KH' : 'NCC';
            const typeClass = item.partner_type === 'customer' ? 'type-customer' : 'type-supplier';
            
            body.innerHTML += `<tr class="${rowClass}" style="cursor:pointer;" onclick="viewDebtDetail('${item.partner_type}', ${item.id})">
                <td><span class="type-badge ${typeClass}">${typeLabel}</span></td>
                <td>${window.WMS.escapeHtml(item.name || '')}</td>
                <td style="text-align:right">${fmtMoney(item.debt_limit || 0)}</td>
                <td style="text-align:right; font-weight:600;">${fmtMoney(item.current_debt)}</td>
            </tr>`;
        });
    } else {
        body.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#999;">Không có dữ liệu</td></tr>';
    }
}

function renderPaymentTable(data) {
    const body = document.getElementById('debt-payments-body');
    body.innerHTML = '';
    if (data && data.length > 0) {
        data.forEach(p => {
            body.innerHTML += `<tr>
                <td>${p.payment_date || ''}</td>
                <td>${p.partner_type === 'customer' ? 'Khách hàng' : 'Nhà cung cấp'}</td>
                <td>${window.WMS.escapeHtml(p.partner_name || '')}</td>
                <td>${window.WMS.escapeHtml(p.order_code || '-')}</td>
                <td style="text-align:right">${fmtMoney(p.amount)}</td>
                <td>${p.payment_method || ''}</td>
                <td>${window.WMS.escapeHtml(p.notes || '')}</td>
            </tr>`;
        });
    } else {
        body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">Không có dữ liệu</td></tr>';
    }
}

function filterDebt() {
    if (currentDebtTab === 'payments') {
        renderPaymentTable(getFilteredPayments());
    } else {
        renderMergedTable(getFilteredPartners());
    }
}

async function loadDebtSummary() {
    try {
        const [custRes, supRes] = await Promise.all([
            window.WMS.api('/debt/customers').catch(() => ({items: []})),
            window.WMS.api('/debt/suppliers').catch(() => ({items: []}))
        ]);
        
        rawCustomers = custRes.items || [];
        rawSuppliers = supRes.items || [];
        
        filterDebt();
    } catch (e) {
        console.error('Lỗi tải dữ liệu công nợ:', e);
    }
}

function viewDebtDetail(partnerType, partnerId) {
    if (partnerType === 'customer') {
        viewCustomerDebt(partnerId);
    } else {
        viewSupplierDebt(partnerId);
    }
}

async function loadPayments() {
    try {
        const res = await window.WMS.api('/debt/payments?limit=100');
        rawPayments = res.items || [];
        filterDebt();
    } catch (e) {
        console.error('Lỗi tải lịch sử thanh toán:', e);
        rawPayments = [];
    }
}

async function viewCustomerDebt(customerId) {
    try {
        const res = await window.WMS.api(`/debt/customers/${customerId}`);
        const c = res.customer;
        let html = `
            <div class="grid grid-cols-2 gap-4" style="margin-bottom:1rem;">
                <div><strong>Mã:</strong> ${window.WMS.escapeHtml(c.code)}</div>
                <div><strong>Tên:</strong> ${window.WMS.escapeHtml(c.name)}</div>
                <div><strong>Điện thoại:</strong> ${window.WMS.escapeHtml(c.phone || '')}</div>
                <div><strong>Loại:</strong> ${window.WMS.escapeHtml(c.customer_type || '')}</div>
                <div><strong>Hạn mức:</strong> ${fmtMoney(c.credit_limit || 0)}</div>
                <div><strong>Công nợ hiện tại:</strong> ${fmtMoney(c.current_debt)}</div>
            </div>
            <h4 style="margin-top:1rem;">Đơn hàng chưa thanh toán hết</h4>
            <table class="simple-table">
                <thead><tr><th>Mã đơn</th><th>Ngày</th><th>Tổng tiền</th><th>Đã TT</th><th>Còn nợ</th><th>Trạng thái</th></tr></thead>
                <tbody>
        `;
        if (res.orders && res.orders.length > 0) {
            res.orders.forEach(o => {
                html += `<tr>
                    <td>${window.WMS.escapeHtml(o.code)}</td>
                    <td>${o.order_date || ''}</td>
                    <td style="text-align:right">${fmtMoney(o.final_amount)}</td>
                    <td style="text-align:right">${fmtMoney(o.paid_amount)}</td>
                    <td style="text-align:right">${fmtMoney(o.remaining_debt)}</td>
                    <td>${o.payment_status || ''}</td>
                </tr>`;
            });
        } else {
            html += '<tr><td colspan="6" style="text-align:center;">Không có đơn hàng nợ</td></tr>';
        }
        html += '</tbody></table>';
        
        if (res.payments && res.payments.length > 0) {
            html += `<h4 style="margin-top:1rem;">Lịch sử thanh toán gần đây</h4>
            <table class="simple-table">
                <thead><tr><th>Ngày</th><th>Số tiền</th><th>Phương thức</th><th>Ghi chú</th></tr></thead>
                <tbody>`;
            res.payments.slice(0, 10).forEach(p => {
                html += `<tr>
                    <td>${p.payment_date || ''}</td>
                    <td style="text-align:right">${fmtMoney(p.amount)}</td>
                    <td>${p.payment_method || ''}</td>
                    <td>${window.WMS.escapeHtml(p.notes || '')}</td>
                </tr>`;
            });
            html += '</tbody></table>';
        }
        
        document.getElementById('modal-title').innerText = `Chi tiết công nợ - ${c.name}`;
        document.getElementById('debt-modal-content').innerHTML = html;
        const el = document.getElementById('debt-modal');
        el.classList.add('active');
        el.setAttribute('aria-hidden', 'false');
        // Nếu đang mở modal thanh toán thì đóng luôn để tránh chồng trạng thái
        closePaymentModal();
        document.body.classList.add('modal-open');

    } catch (e) {
        window.WMS.showToast('Lỗi tải chi tiết: ' + e.message, true);
    }
}

async function viewSupplierDebt(supplierId) {
    try {
        const res = await window.WMS.api(`/debt/suppliers/${supplierId}`);
        const s = res.supplier;
        let html = `
            <div class="grid grid-cols-2 gap-4" style="margin-bottom:1rem;">
                <div><strong>Mã:</strong> ${window.WMS.escapeHtml(s.code)}</div>
                <div><strong>Tên:</strong> ${window.WMS.escapeHtml(s.name)}</div>
                <div><strong>Điện thoại:</strong> ${window.WMS.escapeHtml(s.phone || '')}</div>
                <div><strong>Hạn mức:</strong> ${fmtMoney(s.debt_limit || 0)}</div>
                <div><strong>Công nợ hiện tại:</strong> ${fmtMoney(s.current_debt)}</div>
                <div><strong>Hạn thanh toán:</strong> ${s.payment_terms || 30} ngày</div>
            </div>
            <h4 style="margin-top:1rem;">Đơn nhập chưa thanh toán hết</h4>
            <table class="simple-table">
                <thead><tr><th>Mã phiếu</th><th>Ngày</th><th>Tổng tiền</th><th>Đã TT</th><th>Còn nợ</th><th>Trạng thái</th></tr></thead>
                <tbody>
        `;
        if (res.orders && res.orders.length > 0) {
            res.orders.forEach(o => {
                html += `<tr>
                    <td>${window.WMS.escapeHtml(o.code)}</td>
                    <td>${o.order_date || ''}</td>
                    <td style="text-align:right">${fmtMoney(o.final_amount)}</td>
                    <td style="text-align:right">${fmtMoney(o.paid_amount)}</td>
                    <td style="text-align:right">${fmtMoney(o.remaining_debt)}</td>
                    <td>${o.payment_status || ''}</td>
                </tr>`;
            });
        } else {
            html += '<tr><td colspan="6" style="text-align:center;">Không có đơn hàng nợ</td></tr>';
        }
        html += '</tbody></table>';
        
        if (res.payments && res.payments.length > 0) {
            html += `<h4 style="margin-top:1rem;">Lịch sử thanh toán gần đây</h4>
            <table class="simple-table">
                <thead><tr><th>Ngày</th><th>Số tiền</th><th>Phương thức</th><th>Ghi chú</th></tr></thead>
                <tbody>`;
            res.payments.slice(0, 10).forEach(p => {
                html += `<tr>
                    <td>${p.payment_date || ''}</td>
                    <td style="text-align:right">${fmtMoney(p.amount)}</td>
                    <td>${p.payment_method || ''}</td>
                    <td>${window.WMS.escapeHtml(p.notes || '')}</td>
                </tr>`;
            });
            html += '</tbody></table>';
        }
        
        document.getElementById('modal-title').innerText = `Chi tiết công nợ NCC - ${s.name}`;
        document.getElementById('debt-modal-content').innerHTML = html;
        const el = document.getElementById('debt-modal');
        el.classList.add('active');
        el.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');
    } catch (e) {
        window.WMS.showToast('Lỗi tải chi tiết: ' + e.message, true);
    }
}

function openPaymentModal(partnerType, partnerId, partnerName) {
    document.getElementById('pay-partner-type').value = partnerType;
    document.getElementById('pay-partner-id').value = partnerId;
    document.getElementById('pay-partner-name').value = partnerName;
    document.getElementById('pay-order-type').value = '';
    document.getElementById('pay-order-id').value = '';
    document.getElementById('pay-order-code').value = '';
    document.getElementById('pay-amount').value = '';
    document.getElementById('pay-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('pay-method').value = 'cash';
    document.getElementById('pay-ref').value = '';
    document.getElementById('pay-notes').value = '';

    const el = document.getElementById('payment-modal');
    el.classList.add('active');
    el.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
}


function openPaymentForOrder(partnerType, partnerId, partnerName, orderType, orderId, orderCode, remainingDebt) {
    openPaymentModal(partnerType, partnerId, partnerName);
    document.getElementById('pay-order-type').value = orderType;
    document.getElementById('pay-order-id').value = orderId;
    document.getElementById('pay-order-code').value = orderCode;
    document.getElementById('pay-amount').value = remainingDebt || '';
}

function closePaymentModal() {
    const el = document.getElementById('payment-modal');
    if (!el) return;
    el.classList.remove('active');
    el.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
}

function closeDebtModal() {
    const el = document.getElementById('debt-modal');
    if (!el) return;
    el.classList.remove('active');
    el.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
}


async function submitPayment(e) {
    e.preventDefault();
    const data = {
        partner_type: document.getElementById('pay-partner-type').value,
        partner_id: parseInt(document.getElementById('pay-partner-id').value),
        order_type: document.getElementById('pay-order-type').value || 'export_order',
        order_id: document.getElementById('pay-order-id').value ? parseInt(document.getElementById('pay-order-id').value) : null,
        payment_date: document.getElementById('pay-date').value,
        amount: parseFloat(document.getElementById('pay-amount').value),
        payment_method: document.getElementById('pay-method').value,
        reference_number: document.getElementById('pay-ref').value || null,
        notes: document.getElementById('pay-notes').value || null
    };
    
    if (!data.amount || data.amount <= 0) {
        window.WMS.showToast('Số tiền thanh toán phải lớn hơn 0', true);
        return;
    }
    
    try {
        const res = await window.WMS.api('/debt/payment', 'POST', data);
        window.WMS.showToast('Ghi nhận thanh toán thành công');
        closePaymentModal();
        loadDebtSummary();
        if (currentDebtTab === 'payments') loadPayments();
    } catch (e) {
        window.WMS.showToast('Lỗi: ' + e.message, true);
    }
}

// Initialize
updateFilterOptions();
loadDebtSummary();

// Refresh debt page when import/export deleted elsewhere
async function refreshDebtUI() {
    try {
        // Reset cache to avoid using stale state
        rawCustomers = [];
        rawSuppliers = [];
        rawPayments = [];

        // Ensure tab-dependent UI is consistent
        updateFilterOptions();

        await loadDebtSummary();
        if (currentDebtTab === 'payments') {
            await loadPayments();
        } else {
            filterDebt();
        }
    } catch (e) {
        // ignore
    }
}

window.addEventListener('wms:debt:refresh', () => {
    refreshDebtUI();
});

window.addEventListener('storage', (e) => {
    if (e && e.key === 'wms:debt:refresh_ts') {
        refreshDebtUI();
    }
});

