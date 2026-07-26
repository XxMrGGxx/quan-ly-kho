// ========== DEBT PAYMENT PAGE ==========
// Trang thanh toán công nợ ẩn (chỉ gọi từ debt.html)

let currentPartnerType = 'all';
let selectedPartner = null;
let partnerOrders = [];
let selectedOrderIds = new Set();

// ========== SEARCH PARTNER ==========
const partnerSearch = document.getElementById('partner-search');
const partnerDropdown = document.getElementById('partner-dropdown');
const clearSearchBtn = document.getElementById('clear-search');
let searchDebounceTimer = null;

if (partnerSearch) {
    partnerSearch.addEventListener('input', function () {
        const query = this.value.trim();
        if (clearSearchBtn) {
            clearSearchBtn.style.display = query.length > 0 ? 'flex' : 'none';
        }
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => searchPartners(query), 250);
    });

    partnerSearch.addEventListener('focus', function () {
        const query = this.value.trim();
        if (clearSearchBtn) {
            clearSearchBtn.style.display = query.length > 0 ? 'flex' : 'none';
        }
        searchPartners(query);
    });

    partnerSearch.addEventListener('blur', function () {
        // Delay để click vào dropdown có hiệu quả
        setTimeout(() => { partnerDropdown.style.display = 'none'; }, 150);
    });
}

function clearSearchInput() {
    if (partnerSearch) {
        partnerSearch.value = '';
        partnerSearch.focus();
        if (clearSearchBtn) clearSearchBtn.style.display = 'none';
        searchPartners('');
    }
}

async function searchPartners(keyword) {
    try {
        const res = await window.WMS.api(`/debt/partners/search?type=${encodeURIComponent(currentPartnerType)}&keyword=${encodeURIComponent(keyword)}`);
        const items = res.items || [];
        renderPartnerDropdown(items);
    } catch (e) {
        console.error('Lỗi tìm kiếm đối tác:', e);
    }
}

function renderPartnerDropdown(items) {
    if (!items || items.length === 0) {
        partnerDropdown.innerHTML = '<div class="partner-dropdown-item partner-empty">Không tìm thấy đối tác có nợ</div>';
        partnerDropdown.style.display = 'block';
        return;
    }

    partnerDropdown.innerHTML = items.map((item, idx) => {
        const typeLabel = item.partner_type === 'customer' ? 'Khách hàng' : 'Nhà cung cấp';
        const typeClass = item.partner_type === 'customer' ? 'tag-customer' : 'tag-supplier';
        const typeIcon = item.partner_type === 'customer' ? '👤' : '📦';
        return `<div class="partner-dropdown-item" data-index="${idx}" data-type="${item.partner_type}" data-id="${item.id}">
            <div class="partner-item-main">
                <span class="partner-name">${window.WMS.escapeHtml(item.name)}</span>
                <span class="partner-code">${window.WMS.escapeHtml(item.code)}</span>
            </div>
            <div class="partner-item-meta">
                <span class="partner-tag ${typeClass}">${typeIcon} ${typeLabel}</span>
                ${item.phone ? `<span class="partner-phone">📞 ${window.WMS.escapeHtml(item.phone)}</span>` : ''}
                <span class="partner-debt">${window.WMS.formatCurrency(item.current_debt)}</span>
            </div>
        </div>`;
    }).join('');

    partnerDropdown.style.display = 'block';

    // Bind click
    partnerDropdown.querySelectorAll('.partner-dropdown-item').forEach(el => {
        el.addEventListener('mousedown', (e) => {
            e.preventDefault(); // ngăn blur đóng dropdown trước
            const type = el.dataset.type;
            const id = parseInt(el.dataset.id);
            const name = el.querySelector('.partner-name').textContent;
            selectPartner(type, id, name);
        });
    });
}

async function selectPartner(partnerType, partnerId, partnerName) {
    selectedPartner = { partner_type: partnerType, partner_id: partnerId, name: partnerName };
    partnerSearch.value = partnerName;
    if (clearSearchBtn) clearSearchBtn.style.display = 'flex';
    partnerDropdown.style.display = 'none';

    // Load orders
    try {
        const res = await window.WMS.api(`/debt/orders-to-pay?partner_type=${encodeURIComponent(partnerType)}&partner_id=${partnerId}`);
        partnerOrders = res.orders || [];
        selectedOrderIds.clear();

        // Render header
        document.getElementById('selected-partner-title').textContent = `${partnerType === 'customer' ? 'Khách hàng' : 'Nhà cung cấp'}: ${partnerName}`;
        const debtBadge = document.getElementById('selected-partner-debt');
        debtBadge.textContent = `Công nợ: ${window.WMS.formatCurrency(res.total_debt)}`;
        debtBadge.className = 'debt-badge ' + (res.total_debt > 0 ? 'debt-over-limit' : 'debt-normal');

        // Partner info bar
        const p = res.partner || {};
        document.getElementById('partner-info-bar').innerHTML = `
            <div class="partner-info-item"><span class="info-label">Mã:</span> ${window.WMS.escapeHtml(p.code || '')}</div>
            <div class="partner-info-item"><span class="info-label">Điện thoại:</span> ${window.WMS.escapeHtml(p.phone || '')}</div>
            <div class="partner-info-item"><span class="info-label">Tổng nợ:</span> <strong style="color:#dc2626;">${window.WMS.formatCurrency(res.total_debt)}</strong></div>
            <div class="partner-info-item"><span class="info-label">Số phiếu còn nợ:</span> <strong>${res.order_count}</strong></div>
        `;

        // Show payment section
        document.getElementById('payment-section').style.display = 'block';

        renderOrdersTable();
        updatePaymentSummary();
    } catch (e) {
        window.WMS.showToast('Lỗi tải thông tin đối tác: ' + e.message, true);
    }
}

// ========== RENDER ORDERS ==========
function renderOrdersTable() {
    const tbody = document.getElementById('orders-body');
    tbody.innerHTML = '';

    if (partnerOrders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#999;">Không có đơn hàng còn nợ</td></tr>';
        return;
    }

    partnerOrders.forEach(o => {
        const isSelected = selectedOrderIds.has(o.id);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="text-align:center;">
                <input type="checkbox" class="order-checkbox" data-order-id="${o.id}" data-debt="${o.remaining_debt || 0}" ${isSelected ? 'checked' : ''} onchange="onOrderCheckChanged()">
            </td>
            <td><span class="order-code">${window.WMS.escapeHtml(o.code)}</span></td>
            <td>${window.WMS.formatDateOnly(o.order_date)}</td>
            <td style="text-align:right">${window.WMS.formatCurrency(o.final_amount)}</td>
            <td style="text-align:right">${window.WMS.formatCurrency(o.paid_amount)}</td>
            <td style="text-align:right; color:${(o.remaining_debt || 0) > 0 ? '#dc2626' : '#059669'}; font-weight:700;">${window.WMS.formatCurrency(o.remaining_debt)}</td>
            <td><span class="debt-badge ${o.payment_status === 'paid' ? 'debt-normal' : (o.remaining_debt > 0 ? 'debt-warning' : 'debt-normal')}">${o.payment_status || 'Chưa TT'}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function getSelectedOrderData() {
    const checked = document.querySelectorAll('.order-checkbox:checked');
    const results = [];
    checked.forEach(cb => {
        const orderId = parseInt(cb.dataset.orderId || cb.getAttribute('data-order-id'));
        const debt = parseFloat(cb.dataset.debt || cb.getAttribute('data-debt')) || 0;
        results.push({ order_id: orderId, remaining_debt: debt });
    });
    return results;
}

function updatePaymentSummary() {
    const selected = getSelectedOrderData();
    const count = selected.length;
    const selectedDebt = selected.reduce((sum, x) => sum + x.remaining_debt, 0);

    document.getElementById('summary-selected-count').textContent = count + ' phiếu';
    document.getElementById('summary-selected-debt').textContent = window.WMS.formatCurrency(selectedDebt);
    document.getElementById('summary-total-debt').textContent = window.WMS.formatCurrency(
        partnerOrders.reduce((sum, o) => sum + (o.remaining_debt || 0), 0)
    );
}

function onOrderCheckChanged() {
    const checked = document.querySelectorAll('.order-checkbox:checked');
    selectedOrderIds.clear();
    checked.forEach(cb => {
        const orderId = parseInt(cb.getAttribute('data-order-id'));
        selectedOrderIds.add(orderId);
    });
    updatePaymentSummary();
}

function toggleSelectAll(checked) {
    const checkboxes = document.querySelectorAll('.order-checkbox');
    checkboxes.forEach(cb => { cb.checked = checked; });
    onOrderCheckChanged();
}

// ========== PAYMENT ACTIONS ==========
function filterPartnerType(type) {
    currentPartnerType = type;
    document.querySelectorAll('#partner-filter .filter-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`#partner-filter .filter-btn[data-type="${type}"]`).classList.add('active');

    const query = partnerSearch.value.trim();
    searchPartners(query);
}

function markAllOrders() {
    const checkboxes = document.querySelectorAll('.order-checkbox');
    checkboxes.forEach(cb => { cb.checked = true; });
    onOrderCheckChanged();
}

function unmarkAllOrders() {
    const checkboxes = document.querySelectorAll('.order-checkbox');
    checkboxes.forEach(cb => { cb.checked = false; });
    onOrderCheckChanged();
}

function markByDebtRange() {
    const modal = document.getElementById('debt-range-modal');
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    document.getElementById('debt-range-from').value = '';
    document.getElementById('debt-range-to').value = '';
}

function closeDebtRangeModal() {
    const modal = document.getElementById('debt-range-modal');
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
}

function applyDebtRange() {
    const fromVal = parseFloat(document.getElementById('debt-range-from').value || '0');
    const toVal = parseFloat(document.getElementById('debt-range-to').value || '999999999');

    const checkboxes = document.querySelectorAll('.order-checkbox');
    checkboxes.forEach(cb => {
        const debt = parseFloat(cb.getAttribute('data-debt')) || 0;
        cb.checked = debt >= fromVal && debt <= toVal;
    });
    onOrderCheckChanged();
    closeDebtRangeModal();
}

function quickPay(mode) {
    const checkboxes = document.querySelectorAll('.order-checkbox');
    checkboxes.forEach(cb => {
        const debt = parseFloat(cb.getAttribute('data-debt')) || 0;
        let shouldCheck = false;
        if (mode === 'all') {
            shouldCheck = true;
        } else if (mode === 'unpaid') {
            shouldCheck = debt > 0;
        } else if (mode === 'partial') {
            shouldCheck = debt > 0;
        }
        cb.checked = shouldCheck;
    });
    onOrderCheckChanged();
}

function clearPayment() {
    selectedPartner = null;
    partnerOrders = [];
    selectedOrderIds.clear();
    partnerSearch.value = '';
    if (clearSearchBtn) clearSearchBtn.style.display = 'none';
    document.getElementById('payment-section').style.display = 'none';
    document.getElementById('orders-body').innerHTML = '';
    updatePaymentSummary();
}

// ========== SUBMIT BATCH PAYMENT ==========
async function submitBatchPayment() {
    if (!selectedPartner) {
        window.WMS.showToast('Chưa chọn đối tác', true);
        return;
    }

    const selected = getSelectedOrderData();
    if (selected.length === 0) {
        window.WMS.showToast('Chưa chọn phiếu để thanh toán', true);
        return;
    }

    const amountInput = document.getElementById('payment-amount');
    const totalAmount = parseFloat(amountInput.value || '0');
    if (totalAmount <= 0) {
        window.WMS.showToast('Số tiền thanh toán phải lớn hơn 0', true);
        amountInput.focus();
        return;
    }

    // Confirm
    if (!confirm(`Xác nhận thanh toán ${window.WMS.formatCurrency(totalAmount)} cho ${selected.length} phiếu?`)) {
        return;
    }

    // Phân bổ số tiền cho từng phiếu
    let remainingAmount = totalAmount;
    const payments = selected.map((s, idx) => {
        let allocated = Math.min(s.remaining_debt, remainingAmount);
        remainingAmount -= allocated;
        return {
            order_id: s.order_id,
            amount: Math.round(allocated * 100) / 100
        };
    });

    try {
        const body = {
            partner_type: selectedPartner.partner_type,
            partner_id: selectedPartner.partner_id,
            order_type: selectedPartner.partner_type === 'customer' ? 'export_order' : 'import_order',
            payment_date: new Date().toISOString().split('T')[0],
            payment_method: 'cash',
            reference_number: null,
            notes: `Thanh toán hàng loạt (${selected.length} phiếu)`,
            payments: payments
        };

        const res = await window.WMS.api('/debt/batch-payment', 'POST', body);
        window.WMS.showToast(`Thanh toán thành công: ${window.WMS.formatCurrency(res.total_amount)}`);

        // Refresh partner
        await selectPartner(selectedPartner.partner_type, selectedPartner.partner_id, selectedPartner.name);
        amountInput.value = '';
    } catch (e) {
        window.WMS.showToast('Lỗi thanh toán: ' + e.message, true);
    }
}

// ========== KEYBOARD SHORTCUT ==========
document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        const paymentSection = document.getElementById('payment-section');
        if (paymentSection && paymentSection.style.display !== 'none') {
            submitBatchPayment();
        }
    }
});
