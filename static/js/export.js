function buildQueryString() {
    const fromDate = document.getElementById('from_date')?.value;
    const toDate = document.getElementById('to_date')?.value;
    const params = new URLSearchParams();
    if (fromDate) params.append('from_date', fromDate);
    if (toDate) params.append('to_date', toDate);
    const qs = params.toString();
    return qs ? `?${qs}` : '';
}

async function loadExportOrders() {
    const queryString = buildQueryString();
    const data = await window.WMS.api(`/export_orders${queryString}`);
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    if(data && data.items) {
        data.items.forEach(order => {
            const statusBadge = order.status === 'completed' ? 'badge-success' : 'badge-warning';
            const statusText = order.status === 'completed' ? 'Hoàn thành' : 'Nháp';
            tbody.innerHTML += `
                <tr>
                <td data-label="">
                    <input type="checkbox" class="select_order" data-order-id="${order.id}" />
                </td>
                <td data-label="Mã">${window.WMS.escapeHtml(order.code)}</td>
                <td data-label="KH">${window.WMS.escapeHtml(order.customer_name || '-')}</td>
                    <td data-label="Ngày">${window.WMS.formatDateOnly(order.order_date)}</td>
                    <td data-label="NLP">${window.WMS.escapeHtml(order.created_by_name || '-')}</td>
                    <td data-label="TT"><span class="badge ${statusBadge}">${window.WMS.escapeHtml(statusText)}</span></td>
                    <td data-label="Tổng">${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(order.final_amount))} đ</td>
                    <td data-label="HĐ">
                        ${order.status !== 'completed' ? `<button class="btn btn-success btn-sm" onclick="confirmExport(${order.id})">✅</button>` : ''}
                        <button class="btn btn-secondary btn-sm" onclick="window.location.href='/export/${order.id}/edit'">✏️</button>
                        <button class="btn btn-secondary btn-sm" onclick="viewExportDetail(${order.id})">👁️</button>
                        <button class="btn btn-danger btn-sm" onclick="deleteExportOrder(${order.id})">🗑️</button>

                    </td>
                </tr>
            `;
        });
    }
}

async function confirmExport(orderId) {
    // lấy setting cho phép xuất kho âm
    let allowNegative = false;
    try {
        const data = await window.WMS.api('/inventory/settings');
        allowNegative = !!data?.settings?.allow_negative_stock;
    } catch (e) {
        // nếu không lấy được setting thì fallback: không cho phép xuất âm
        allowNegative = false;
    }

    if (allowNegative) {
        const confirmed1 = await window.WMS.confirm('Cảnh báo: cho phép xuất kho âm. Hệ thống sẽ trừ tồn và có thể tạo tồn kho âm.');
        if (!confirmed1) return;

        const confirmed2 = await window.WMS.confirm('Xác nhận bắt buộc: Bạn thật sự muốn xuất kho làm tồn kho âm?');
        if (!confirmed2) return;

        const result = await window.WMS.api(`/export_orders/${orderId}/confirm`, 'PUT', { confirm_negative_stock: true });
        if (result) {
            if (result.debt_warnings && result.debt_warnings.length > 0) {
                window.WMS.showToast('Đã xác nhận xuất kho (có cảnh báo công nợ)', false);
                window.WMS.toast.warning('Cảnh báo công nợ', result.debt_warnings.join('\n'));
            } else {
                window.WMS.showToast('Đã xác nhận xuất kho');
            }
            loadExportOrders();
        }
    } else {
        const confirmed = await window.WMS.confirm('Xác nhận xuất kho? Hàng sẽ được trừ khỏi tồn kho.');
        if (confirmed) {
            const result = await window.WMS.api(`/export_orders/${orderId}/confirm`, 'PUT');
            if (result) {
                if (result.debt_warnings && result.debt_warnings.length > 0) {
                    window.WMS.showToast('Đã xác nhận xuất kho (có cảnh báo công nợ)', false);
                    window.WMS.toast.warning('Cảnh báo công nợ', result.debt_warnings.join('\n'));
                } else {
                    window.WMS.showToast('Đã xác nhận xuất kho');
                }
                try {
                    window.dispatchEvent(new CustomEvent('wms:debt:refresh'));
                    localStorage.setItem('wms:debt:refresh_ts', String(Date.now()));
                } catch (e) {}
                loadExportOrders();
            }
        }
    }
}


async function deleteExportOrder(orderId) {
    const confirmed = await window.WMS.confirm('Bạn có chắc chắn muốn xóa phiếu xuất này? Hành động này không thể hoàn tác.');
    if (confirmed) {
        const result = await window.WMS.api(`/export_orders/${orderId}`, 'DELETE');
        if(result) {
            window.WMS.showToast('Đã xóa phiếu xuất thành công');
            loadExportOrders();
            // notify debt page to refresh
            try {
                window.dispatchEvent(new CustomEvent('wms:debt:refresh'));
                localStorage.setItem('wms:debt:refresh_ts', String(Date.now()));
            } catch (e) {}

        }
    }
}

function showExportDetailModal(order, items) {
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
            <div><strong>Khách hàng:</strong> ${window.WMS.escapeHtml(order.customer_name || '-')}</div>
            <div><strong>Ngày xuất:</strong> ${window.WMS.formatDateOnly(order.order_date)}</div>
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
                <h3>Chi tiết phiếu xuất ${window.WMS.escapeHtml(order.code)}</h3>
                <button class="modal-close-btn" onclick="window.WMS.closeModal('wms-detail-modal');setTimeout(()=>document.getElementById('wms-detail-modal')?.remove(),300);">Dong</button>
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

async function viewExportDetail(orderId) {
    try {
        const data = await window.WMS.api(`/export_orders/${orderId}`);
        if (data) {
            const order = data.order || data;
            const items = data.items || [];
            showExportDetailModal(order, items);
        }
    } catch (error) {
        window.WMS.showToast('Lỗi tải chi tiết: ' + error.message, true);
    }
}

function toggleSelectAll(checkbox) {
    const checked = checkbox.checked;
    document.querySelectorAll('input.select_order').forEach(cb => {
        cb.checked = checked;
    });
}

async function exportSelectedToExcel() {
    const selected = [...document.querySelectorAll('input.select_order:checked')].map(cb => cb.dataset.orderId);
    if (!selected.length) {
        window.WMS.showToast('Chưa chọn phiếu xuất', true);
        return;
    }
    const token = localStorage.getItem('wms_token');
    const url = '/api/export_orders/excel-batch';
    const qs = token ? ('?token=' + encodeURIComponent(token)) : '';
    const idsQuery = `order_ids=${encodeURIComponent(selected.join(','))}`;
    const finalQs = qs ? `${qs}&${idsQuery}` : `?${idsQuery}`;
    window.open(`${url}${finalQs}`, '_blank');

}


// Lọc ngay khi thay đổi từ ngày / đến ngày
['from_date','to_date'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => loadExportOrders());
});

loadExportOrders();