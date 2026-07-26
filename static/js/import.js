async function loadImportOrders() {
    const data = await window.WMS.api('/import_orders');
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    if(data && data.items) {
        data.items.forEach(order => {
            const statusBadge = order.status === 'completed' ? 'badge-success' : 'badge-warning';
            const statusText = order.status === 'completed' ? 'Hoàn thành' : 'Nháp';
            tbody.innerHTML += `
                <tr>
                    <td data-label="Mã">
                        <input type="checkbox" class="select_order" data-order-id="${order.id}" />
                    </td>
                    <td data-label="Mã">${window.WMS.escapeHtml(order.code)}</td>
                    <td data-label="NCC">${window.WMS.escapeHtml(order.supplier_name || '-')}</td>
                    <td data-label="Ngày">${window.WMS.formatDateOnly(order.order_date)}</td>
                    <td data-label="NLP">${window.WMS.escapeHtml(order.created_by_name || '-')}</td>
                    <td data-label="TT"><span class="badge ${statusBadge}">${window.WMS.escapeHtml(statusText)}</span></td>
                    <td data-label="Tổng">${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(order.final_amount))} đ</td>
                    <td data-label="HĐ">
                        ${order.status !== 'completed' ? `<button class="btn btn-success btn-sm" onclick="confirmImport(${order.id})">✅</button>` : ''}
                        <button class="btn btn-secondary btn-sm" onclick="window.location.href='/import/${order.id}/edit'">✏️</button>
                        <button class="btn btn-secondary btn-sm" onclick="viewImportDetail(${order.id})">👁️</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteImportOrder(${order.id})">🗑️</button>
                    </td>
                </tr>
            `;
        });
    }
}

function toggleSelectAll(checkbox) {
    const checked = checkbox.checked;
    document.querySelectorAll('input.select_order').forEach(cb => {
        cb.checked = checked;
    });
}

function exportSelectedToExcel() {
    const selected = [...document.querySelectorAll('input.select_order:checked')].map(cb => cb.dataset.orderId);
    if (!selected.length) {
        window.WMS.showToast('Chưa chọn phiếu nhập', true);
        return;
    }

    // Hiện backend chưa có endpoint excel-batch cho import, nên xuất theo từng phiếu bằng cách tải lần lượt.
    // Cách đơn giản: mở export cho từng phiếu. (Nếu bạn có API excel-batch, thay bằng 1 request.)
    const token = localStorage.getItem('wms_token');
    selected.forEach(orderId => {
        let url = `/api/import_orders/${orderId}/excel`;
        if (token) url += (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
        window.open(url, '_blank');
    });
}


async function confirmImport(orderId) {
    const confirmed = await window.WMS.confirm('Xác nhận nhập kho? Hàng sẽ được cập nhật vào tồn kho.');
    if (confirmed) {
        const result = await window.WMS.api(`/import_orders/${orderId}/confirm`, 'PUT');
        if(result) {
            if (result.debt_warnings && result.debt_warnings.length > 0) {
                window.WMS.showToast('Đã xác nhận nhập kho (có cảnh báo công nợ)', false);
                window.WMS.toast.warning('Cảnh báo công nợ', result.debt_warnings.join('\n'));
            } else {
                window.WMS.showToast('Đã xác nhận nhập kho');
            }
            try {
                window.dispatchEvent(new CustomEvent('wms:debt:refresh'));
                localStorage.setItem('wms:debt:refresh_ts', String(Date.now()));
            } catch (e) {}
            loadImportOrders();
        }
    }
}

async function deleteImportOrder(orderId) {
    const confirmed = await window.WMS.confirm('Bạn có chắc chắn muốn xóa phiếu nhập này? Hành động này không thể hoàn tác.');
    if (confirmed) {
        const result = await window.WMS.api(`/import_orders/${orderId}`, 'DELETE');
        if(result) {
            window.WMS.showToast('Đã xóa phiếu nhập thành công');
            loadImportOrders();
            // notify debt page to refresh
            try {
                window.dispatchEvent(new CustomEvent('wms:debt:refresh'));
                localStorage.setItem('wms:debt:refresh_ts', String(Date.now()));
            } catch (e) {}

        }
    }
}

function showImportDetailModal(order, items) {
    // Remove existing detail modal if any
    const existing = document.getElementById('wms-detail-modal');
    if (existing) existing.remove();
    
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'wms-detail-modal';
    overlay.style.cssText = 'display:flex;';
    
    let bodyHtml = `<div style="background:#f8fafc;padding:16px;border-radius:8px;margin-bottom:16px;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div><strong>Mã phiếu:</strong> ${window.WMS.escapeHtml(order.code)}</div>
            <div><strong>Nhà cung cấp:</strong> ${window.WMS.escapeHtml(order.supplier_name || '-')}</div>
            <div><strong>Ngày nhập:</strong> ${window.WMS.formatDateOnly(order.order_date)}</div>
            <div><strong>Trạng thái:</strong> <span class="badge ${order.status === 'completed' ? 'badge-success' : 'badge-warning'}">${order.status === 'completed' ? 'Hoàn thành' : 'Nháp'}</span></div>
            <div><strong>Tổng tiền:</strong> ${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(order.final_amount))} đ</div>
            <div><strong>Ghi chú:</strong> ${window.WMS.escapeHtml(order.notes || '-')}</div>
        </div>
    </div>`;
    
    if (items.length > 0) {
        bodyHtml += `<h4 style="margin-bottom:8px;">Danh sách sản phẩm</h4>
        <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#f1f5f9;">
                <th style="padding:8px;text-align:left;">STT</th>
                <th style="padding:8px;text-align:left;">Sản phẩm</th>
                <th style="padding:8px;text-align:right;">Số lượng</th>
                <th style="padding:8px;text-align:right;">Đơn giá</th>
                <th style="padding:8px;text-align:right;">Thành tiền</th>
            </tr></thead>
            <tbody>${items.map((item, idx) => `
                <tr style="border-bottom:1px solid #e2e8f0;">
                    <td style="padding:8px;">${idx + 1}</td>
                    <td style="padding:8px;">${window.WMS.escapeHtml(item.product_name || item.code || '-')}</td>
                            <td style="padding:8px;text-align:right;">${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(item.quantity_ordered || item.quantity))}</td>
                    <td style="padding:8px;text-align:right;">${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(item.unit_price))} đ</td>
                    <td style="padding:8px;text-align:right;">${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(item.total_price))} đ</td>
                </tr>`).join('')}
            </tbody>
        </table>`;
    }
    
    overlay.innerHTML = `
        <div class="modal-content modal-lg" style="transform:translateY(0);opacity:1;">
            <div class="modal-header">
                <h3>Chi tiết phiếu nhập ${window.WMS.escapeHtml(order.code)}</h3>
                <button class="modal-close-btn" onclick="window.WMS.closeModal('wms-detail-modal');setTimeout(()=>document.getElementById('wms-detail-modal')?.remove(),300);">✕</button>
            </div>
            <div class="modal-body" style="font-size:14px;color:#475569;">
                ${bodyHtml}
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="window.WMS.closeModal('wms-detail-modal');setTimeout(()=>document.getElementById('wms-detail-modal')?.remove(),300);">Đóng</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(overlay);
    document.body.classList.add('modal-open');
    
    requestAnimationFrame(() => overlay.classList.add('active'));
    
    overlay.addEventListener('click', function(e) {
        if (e.target === this) {
            window.WMS.closeModal('wms-detail-modal');
            setTimeout(() => overlay.remove(), 300);
        }
    });
}

async function viewImportDetail(orderId) {
    try {
        const data = await window.WMS.api(`/import_orders/${orderId}`);
        if (data) {
            const order = data.order || data;
            const items = data.items || [];
            showImportDetailModal(order, items);
        }
    } catch (error) {
        window.WMS.showToast('Lỗi tải chi tiết: ' + error.message, true);
    }
}

function downloadTemplate() {
    const token = localStorage.getItem('wms_token');
    let url = `/api/import_orders/excel-template`;
    if (token) url += (url.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
    window.open(url, '_blank');
}

function showImportExcelModal() {
    const existing = document.getElementById('wms-import-excel-modal');
    if (existing) existing.remove();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'wms-import-excel-modal';
    overlay.style.cssText = 'display:flex;';
    overlay.innerHTML = `
        <div class="modal-content modal-md" style="transform:translateY(0);opacity:1;">
            <div class="modal-header">
                <h3>Nhập phiếu nhập từ Excel</h3>
                <button class="modal-close-btn" onclick="closeImportExcelModal()">✕</button>
            </div>
            <div class="modal-body" style="font-size:14px;color:#475569;">
                <p style="margin-bottom:12px;">Chọn file Excel chứa danh sách sản phẩm nhập kho. Tải mẫu <a href="javascript:void(0)" onclick="downloadTemplate()" style="color:#2563eb;">tại đây</a>.</p>
                <div>
                    <label style="font-weight:600;display:block;margin-bottom:6px;">File Excel (.xlsx)</label>
                    <input type="file" id="import-excel-file" accept=".xlsx,.xls" class="input" style="padding:8px;">
                </div>
                <div style="margin-top:12px;color:#64748b;font-size:13px;">
                    Mỗi dòng là 1 sản phẩm. Cột: Mã SP (hoặc tên SP), Số lượng, Đơn giá, ĐVT, Ghi chú.
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeImportExcelModal()">Hủy</button>
                <button class="btn btn-primary" onclick="processImportExcel()">📤 Tải lên và tạo phiếu</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    document.body.classList.add('modal-open');
    requestAnimationFrame(() => overlay.classList.add('active'));
    overlay.addEventListener('click', function(e) {
        if (e.target === this) closeImportExcelModal();
    });
}

function closeImportExcelModal() {
    const modal = document.getElementById('wms-import-excel-modal');
    if (modal) {
        window.WMS.closeModal('wms-import-excel-modal');
        setTimeout(() => modal.remove(), 300);
    }
}

async function processImportExcel() {
    const fileInput = document.getElementById('import-excel-file');
    const file = fileInput?.files?.[0];
    if (!file) { window.WMS.showToast('Vui lòng chọn file Excel', true); return; }
    const btn = document.querySelector('#wms-import-excel-modal .btn-primary');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Đang xử lý...'; }
try {
        const formData = new FormData();
        formData.append('file', file);
        const token = localStorage.getItem('wms_token');
        const headers = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        // Thêm CSRF token từ embedded script (httponly cookie - JS không đọc được cookie)
        if (window.WMS && window.WMS.csrfToken) {
            headers['X-CSRF-Token'] = window.WMS.csrfToken;
        }
        const response = await fetch('/api/import_orders/from-excel', { method: 'POST', headers, body: formData, credentials: 'include' });
        if (!response.ok) { const err = await response.json().catch(()=>({})); throw new Error(err.detail || `HTTP ${response.status}`); }
        const result = await response.json();
        window.WMS.showToast(result.message || 'Nhập từ Excel thành công');
        closeImportExcelModal();
        if (result.order_id) {
            window.location.href = `/import/${result.order_id}/edit`;
        } else {
            loadImportOrders();
        }
    } catch (error) {
        window.WMS.showToast(error.message || 'Lỗi xử lý file Excel', true);
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '📤 Tải lên và tạo phiếu'; }
    }
}

loadImportOrders();