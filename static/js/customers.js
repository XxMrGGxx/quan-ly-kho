
let currentCustomerId = null;
let currentSearch = '';

async function loadCustomers(search = null) {
    if (search !== null) currentSearch = search;
    const tbody = document.getElementById('customers-table');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="7"><div class="spinner"></div> Đang tải...</td></tr>';
    
    try {
        const data = await window.WMS.api(`/customers?search=${encodeURIComponent(currentSearch)}`);
        if (data && data.items) {
            if (data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">👤 Không có khách hàng</td></tr>';
            } else {
                tbody.innerHTML = '';
                data.items.forEach(c => {
                    tbody.innerHTML += `
                        <tr>
                            <td data-label="Mã">${window.WMS.escapeHtml(c.code || '-')}</td>
                            <td data-label="Tên"><strong>${window.WMS.escapeHtml(c.name || '')}</strong></td>
                            <td data-label="ĐT">${window.WMS.escapeHtml(c.phone || '-')}</td>
                            <td data-label="Email">${window.WMS.escapeHtml(c.email || '-')}</td>
                            <td data-label="Địa chỉ">${window.WMS.escapeHtml(c.address || '-')}</td>
                            <td data-label="Nợ">${new Intl.NumberFormat('vi-VN').format(window.WMS.safeNumber(c.current_debt))} đ</td>
                            <td data-label="HĐ">
                                <button class="btn btn-secondary btn-sm" onclick="editCustomer(${c.id})">✏️</button>
                                <button class="btn btn-danger btn-sm" onclick="deleteCustomer(${c.id})">🗑️</button>
                            </td>
                         </tr>
                    `;
                });
            }
        }
    } catch (error) {
        tbody.innerHTML = `<tr><td colspan="7" style="color:red;">❌ Lỗi: ${window.WMS.escapeHtml(error.message)}</td></tr>`;
    }
}

const searchInput = document.getElementById('search-input');
if (searchInput) {
    searchInput.addEventListener('input', window.debounce(function(e) {
        loadCustomers(e.target.value);
    }, 500));
}

async function editCustomer(id) {
    // saler không được phép sửa/xóa (đảm bảo UI không mở modal sửa)
    try {
        const me = await window.WMS.api('/auth/me');
        if (me?.role === 'saler') {
            window.WMS.showToast('Bạn không có quyền sửa khách hàng', true);
            return;
        }

        const data = await window.WMS.api('/customers');
        const customer = data?.items?.find(c => c.id === id);
        if (customer) {
            document.getElementById('modalTitle').innerText = '✏️ Sửa khách hàng';
            document.getElementById('cust_name').value = customer.name || '';
            document.getElementById('cust_contact').value = customer.contact_person || '';
            document.getElementById('cust_phone').value = customer.phone || '';
            document.getElementById('cust_email').value = customer.email || '';
            document.getElementById('cust_address').value = customer.address || '';
            document.getElementById('cust_city').value = customer.city || '';
            document.getElementById('cust_tax').value = customer.tax_code || '';
            currentCustomerId = customer.id;
            window.WMS.openModal('customerModal');
        }
    } catch (error) {
        window.WMS.showToast('Lỗi tải thông tin', true);
    }
}

async function deleteCustomer(id) {
    // saler không được phép sửa/xóa
    try {
        const me = await window.WMS.api('/auth/me');
        if (me?.role === 'saler') {
            window.WMS.showToast('Bạn không có quyền xóa khách hàng', true);
            return;
        }

        const confirmed = await window.WMS.confirm('Xóa khách hàng này?');
        if (confirmed) {
            await window.WMS.api(`/customers/${id}`, 'DELETE');
            window.WMS.showToast('Đã xóa');
            loadCustomers(currentSearch);
        }
    } catch (error) {
        window.WMS.showToast('Lỗi xóa khách hàng', true);
    }
}


function openCustomerModal() {
    document.getElementById('customerForm').reset();
    document.getElementById('modalTitle').innerText = '👤 Thêm khách hàng';
    currentCustomerId = null;
    window.WMS.openModal('customerModal');
}

function closeCustomerModal() {
    window.WMS.closeModal('customerModal');
    currentCustomerId = null;
}
document.getElementById('customerForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        name: document.getElementById('cust_name').value,
        contact_person: document.getElementById('cust_contact').value,
        phone: document.getElementById('cust_phone').value,
        email: document.getElementById('cust_email').value,
        address: document.getElementById('cust_address').value,
        city: document.getElementById('cust_city').value,
        tax_code: document.getElementById('cust_tax').value
    };
    
    if (currentCustomerId) {
        await window.WMS.api(`/customers/${currentCustomerId}`, 'PUT', data);
    } else {
        await window.WMS.api('/customers', 'POST', data);
    }
    closeCustomerModal();
    loadCustomers(currentSearch);
    window.WMS.showToast('Lưu thành công');
});

loadCustomers('');