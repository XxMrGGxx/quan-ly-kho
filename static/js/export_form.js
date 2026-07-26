
let allCustomers=[];
// Xác định mode và order_id từ URL path
const PATH_MATCH = window.location.pathname.match(/^\/export\/(\d+)\/edit$/);
const MODE = PATH_MATCH ? 'edit' : 'create';
const ORDER_ID = PATH_MATCH ? parseInt(PATH_MATCH[1]) : null;

async function init(){
  // Hiển thị người lập phiếu từ thông tin user đang đăng nhập
  const userStr = localStorage.getItem('wms_user');
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      document.getElementById('created_by_display').textContent = user.full_name || user.username || '';
    } catch(e) {}
  }
  await loadCustomers(); document.getElementById('order_date').value = new Date().toISOString().split('T')[0]; addItemRow(); if (MODE === 'edit' && ORDER_ID) await loadOrder(); document.getElementById('exportForm').addEventListener('submit', submitForm);
}
async function loadCustomers(){ const d=await window.WMS.api('/customers'); allCustomers=d?.items||[]; document.getElementById('customer_id').innerHTML='<option value="">Chọn khách hàng</option>'+allCustomers.map(c=>window.WMS.optionHtml(c.id, `${c.code || '-'} - ${c.name || '-'}`)).join(''); }
function addItemRow(item={}){
  const row=document.createElement('div'); row.className='item-row';
  row.style.cssText='display:grid;grid-template-columns:56px 2.2fr .9fr 1fr 1fr .8fr 1fr 52px;gap:8px;align-items:center;margin-bottom:8px;';
  const acContainer=document.createElement('div'); acContainer.className='product-ac-container';
  row.innerHTML=`<input class="input stt" readonly><input class="input unit_name" value="${item.unit_name||''}" readonly><input class="input quantity" type="number" min="0" step="0.01" value="${item.quantity_ordered||1}"><input class="input unit_price" type="number" min="0" step="0.01" value="${item.unit_price||''}"><input class="input discount_rate" type="number" min="0" max="100" step="0.01" value="${item.discount_rate||0}"><input class="input line_total" readonly><button type="button" class="btn btn-danger btn-sm">X</button>`;
  row.insertBefore(acContainer, row.querySelector('.unit_name'));
  const ac = window.WMS.createProductAutocomplete(acContainer, {initialText: item.product_text||'', initialValue: item.product_id||'', onSelect:(product)=>{row.ac.selectedProduct=product; compute(row);}});
  row.ac = ac;
  if (item.selectedProduct) {
    row.ac.selectedProduct = item.selectedProduct;
  } else if (item.warehouse_id) {
    row.ac.selectedProduct = { warehouse_id: item.warehouse_id };
  }
  row.querySelector('.btn-danger').onclick=()=>{row.remove(); refresh(); updateTotals();};
  ['quantity','unit_price','discount_rate'].forEach(cls=>row.querySelector('.'+cls).addEventListener('input',()=>compute(row)));
  document.getElementById('items-list').appendChild(row); refresh(); compute(row);
}
function compute(row){ const qty=parseFloat(row.querySelector('.quantity').value||0); const price=parseFloat(row.querySelector('.unit_price').value||0); const rate=parseFloat(row.querySelector('.discount_rate').value||0); const gross=qty*price; row.querySelector('.line_total').value=new Intl.NumberFormat('vi-VN').format(gross - gross*rate/100); updateTotals(); }
function refresh(){ document.querySelectorAll('#items-list .item-row').forEach((r,i)=>r.querySelector('.stt').value=i+1); }
function updateTotals(){ let total=0; document.querySelectorAll('#items-list .item-row').forEach(r=>{ const qty=parseFloat(r.querySelector('.quantity').value||0); const price=parseFloat(r.querySelector('.unit_price').value||0); const rate=parseFloat(r.querySelector('.discount_rate').value||0); const gross=qty*price; total += gross - gross*rate/100;}); document.getElementById('preview-total').value=new Intl.NumberFormat('vi-VN').format(total)+' đ';}
async function loadOrder(){
  const data=await window.WMS.api(`/export_orders/${ORDER_ID}`); const order=data?.order||{}; const items=data?.items||[];
  document.getElementById('customer_id').value=order.customer_id||'';
  document.getElementById('order_date').value=(order.order_date||'').split('T')[0]||document.getElementById('order_date').value;
  document.getElementById('expected_date').value=(order.expected_date||'').split('T')[0]||''; document.getElementById('shipping_address').value=order.shipping_address||'';
  document.getElementById('reference_number').value=order.reference_number||''; document.getElementById('discount_amount').value=order.discount_amount||0;
  document.getElementById('paid_amount').value=order.paid_amount||0; document.getElementById('payment_method').value=order.payment_method||'cash'; document.getElementById('notes').value=order.notes||'';
  document.getElementById('items-list').innerHTML='';
  for (const it of items) {
    let product_text='';
    let warehouse_name='';
    let selectedProduct = null;
    try { const p=await window.WMS.api(`/products/${it.product_id}`); if(p) { product_text=(p.code||'')+' - '+(p.name||''); warehouse_name=p.warehouse_name||''; selectedProduct = { ...p, warehouse_id: p.warehouse_id ?? it.warehouse_id ?? 1 }; } } catch(e) {}
    addItemRow({...it, product_text, warehouse_name, selectedProduct});
  }
}
async function submitForm(e){
  e.preventDefault();
  const items=[...document.querySelectorAll('#items-list .item-row')].map(r=>{ const pid=r.ac?r.ac.getValue():0; const wh_id=r.ac&&r.ac.selectedProduct?r.ac.selectedProduct.warehouse_id:1; const qty=parseFloat(r.querySelector('.quantity').value||0); const price=parseFloat(r.querySelector('.unit_price').value||0); const rate=parseFloat(r.querySelector('.discount_rate').value||0); const gross=qty*price; return {product_id:pid,warehouse_id:wh_id,quantity:qty,unit_price:price,discount_rate:rate,total_price:gross-gross*rate/100};}).filter(x=>x.product_id&&x.quantity>0);
  const payload={partner_id:parseInt(document.getElementById('customer_id').value),order_date:document.getElementById('order_date').value,expected_date:document.getElementById('expected_date').value||null,shipping_address:document.getElementById('shipping_address').value||'',reference_number:document.getElementById('reference_number').value||'',discount_amount:parseFloat(document.getElementById('discount_amount').value||0),paid_amount:parseFloat(document.getElementById('paid_amount').value||0),payment_method:document.getElementById('payment_method').value,notes:document.getElementById('notes').value||'',items};
  const url=MODE==='edit'&&ORDER_ID?`/export_orders/${ORDER_ID}`:'/export_orders'; const method=MODE==='edit'&&ORDER_ID?'PUT':'POST'; const result=await window.WMS.api(url,method,payload); if(result){ try{ window.dispatchEvent(new CustomEvent('wms:debt:refresh')); localStorage.setItem('wms:debt:refresh_ts', String(Date.now())); } catch(e){} window.location.href='/export'; }
}
init();
