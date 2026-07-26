let allSuppliers = [];
const MODE = (typeof MODE_TEMPLATE !== 'undefined') ? MODE_TEMPLATE : null;
const ORDER_ID = (typeof ORDER_ID_TEMPLATE !== 'undefined') ? ORDER_ID_TEMPLATE : null;

async function init(){
  // Hiển thị người lập phiếu từ thông tin user đang đăng nhập
  const userStr = localStorage.getItem('wms_user');
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      document.getElementById('created_by_display').textContent = user.full_name || user.username || '';
    } catch(e) {}
  }
  await loadSuppliers();
  document.getElementById('order_date').value = new Date().toISOString().split('T')[0];
  addItemRow();
  if (MODE === 'edit' && ORDER_ID) await loadOrder();
  document.getElementById('importForm').addEventListener('submit', submitForm);
}

async function loadSuppliers(){
  const d = await window.WMS.api('/suppliers');
  allSuppliers = d?.items || [];
  document.getElementById('supplier_id').innerHTML = '<option value="">Chọn nhà cung cấp</option>' + allSuppliers.map(s => window.WMS.optionHtml(s.id, `${s.code || '-'} - ${s.name || '-'}`)).join('');
}

function addItemRow(item = {}){
  const row = document.createElement('div');
  row.className = 'item-row';
  const acContainer = document.createElement('div');
  acContainer.className = 'product-ac-container';
  row.style.display = 'grid';
  row.style.gridTemplateColumns = '56px 2.5fr .9fr 1fr 1fr 1fr 52px';
  row.style.gap = '8px';
  row.style.alignItems = 'center';
  row.style.marginBottom = '4px';
  row.innerHTML = `<input class="input stt" readonly><input class="input unit_name" value="${item.unit_name || ''}" readonly><input class="input quantity" type="number" min="0" step="0.01" value="${item.quantity_ordered || 1}"><input class="input unit_price" type="number" min="0" step="0.01" value="${item.unit_price || ''}"><input class="input line_total" readonly><button type="button" class="btn btn-danger btn-sm">X</button>`;
  row.insertBefore(acContainer, row.querySelector('.unit_name'));
  const ac = window.WMS.createProductAutocomplete(acContainer, {
    initialText: item.product_text || '',
    initialValue: item.product_id || '',
    onSelect: (product) => { row.ac.selectedProduct = product; compute(row); }
  });
  row.ac = ac;
  row.querySelector('.btn-danger').onclick = () => { row.remove(); refresh(); };
  ['quantity', 'unit_price'].forEach(cls => row.querySelector('.' + cls).addEventListener('input', () => compute(row)));
  document.getElementById('items-list').appendChild(row);
  refresh();
  compute(row);
}

function compute(row){
  const qty = parseFloat(row.querySelector('.quantity').value || 0);
  const price = parseFloat(row.querySelector('.unit_price').value || 0);
  row.querySelector('.line_total').value = new Intl.NumberFormat('vi-VN').format(qty * price);
  refresh();
}

function refresh(){
  document.querySelectorAll('#items-list .item-row').forEach((r, i) => r.querySelector('.stt').value = i + 1);
}

async function loadOrder(){
  const data = await window.WMS.api(`/import_orders/${ORDER_ID}`);
  const order = data?.order || {};
  const items = data?.items || [];
  document.getElementById('supplier_id').value = order.supplier_id || '';
  document.getElementById('order_date').value = (order.order_date || '').split('T')[0] || document.getElementById('order_date').value;
  document.getElementById('discount_amount').value = order.discount_amount || 0;
  document.getElementById('paid_amount').value = order.paid_amount || 0;
  document.getElementById('payment_method').value = order.payment_method || 'cash';
  document.getElementById('notes').value = order.notes || '';
  document.getElementById('items-list').innerHTML = '';
  // Fetch product details for item_text
  for (const it of items) {
    let product_text = '';
    let warehouse_name = '';
    try {
      const p = await window.WMS.api(`/products/${it.product_id}`);
      if (p) {
        product_text = (p.code || '') + ' - ' + (p.name || '');
        warehouse_name = p.warehouse_name || '';
      }
    } catch(e) {}
    addItemRow({ ...it, product_text, warehouse_name });
  }
}

async function submitForm(e){
  e.preventDefault();
  const items = [...document.querySelectorAll('#items-list .item-row')].map(r => {
    const pid = r.ac ? r.ac.getValue() : 0;
    const wh_id = r.ac && r.ac.selectedProduct ? r.ac.selectedProduct.warehouse_id : 1;
    const unitPrice = parseFloat(r.querySelector('.unit_price').value || 0);
    const qty = parseFloat(r.querySelector('.quantity').value || 0);
    return { product_id: pid, warehouse_id: wh_id, quantity: qty, unit_price: unitPrice, total_price: qty * unitPrice };
  }).filter(x => x.product_id && x.quantity > 0);
  const payload = {
    partner_id: parseInt(document.getElementById('supplier_id').value),
    order_date: document.getElementById('order_date').value,
    discount_amount: parseFloat(document.getElementById('discount_amount').value || 0),
    paid_amount: parseFloat(document.getElementById('paid_amount').value || 0),
    payment_method: document.getElementById('payment_method').value,
    notes: document.getElementById('notes').value || '',
    items
  };
  const url = MODE === 'edit' && ORDER_ID ? `/import_orders/${ORDER_ID}` : '/import_orders';
  const method = MODE === 'edit' && ORDER_ID ? 'PUT' : 'POST';
  const result = await window.WMS.api(url, method, payload);
  if (result) {
    try {
      window.dispatchEvent(new CustomEvent('wms:debt:refresh'));
      localStorage.setItem('wms:debt:refresh_ts', String(Date.now()));
    } catch (e) {}
    window.location.href = '/import';
  }
}

init();