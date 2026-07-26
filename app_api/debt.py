"""
Công nợ - Debt Management Module
Quản lý công nợ khách hàng và nhà cung cấp
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from database import get_db
from app_api.auth import get_current_user, check_permission
from app_api.date_utils import normalize_date_yyyy_mm_dd

router = APIRouter()


class PaymentCreate(BaseModel):
    partner_type: str  # 'customer' or 'supplier'
    partner_id: int
    order_type: str  # 'import_order' or 'export_order'
    order_id: Optional[int] = None
    payment_date: str = ""
    amount: float
    payment_method: str = "cash"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class BatchPaymentItem(BaseModel):
    order_id: int
    amount: float


class BatchPaymentCreate(BaseModel):
    partner_type: str  # 'customer' or 'supplier'
    partner_id: int
    order_type: str  # 'import_order' or 'export_order'
    payment_date: str = ""
    payment_method: str = "cash"
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    payments: List[BatchPaymentItem]


def _calculate_customer_debt(conn, customer_id: int) -> float:
    """Tính công nợ hiện tại của khách hàng từ các phiếu xuất thực tế."""
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(COALESCE(final_amount, 0) - COALESCE(paid_amount, 0)), 0) as total_debt
        FROM export_orders
        WHERE customer_id = ? AND status IN ('completed', 'shipped')
    """, (customer_id,))
    return round(float(c.fetchone()[0] or 0), 2)


def _calculate_supplier_debt(conn, supplier_id: int) -> float:
    """Tính công nợ hiện tại của nhà cung cấp từ các phiếu nhập thực tế."""
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(COALESCE(final_amount, 0) - COALESCE(paid_amount, 0)), 0) as total_debt
        FROM import_orders
        WHERE supplier_id = ? AND status = 'completed'
    """, (supplier_id,))
    return round(float(c.fetchone()[0] or 0), 2)


def _sync_customer_debt(conn, customer_id: int):
    """Cập nhật bản tóm tắt current_debt cho khách hàng từ dữ liệu phiếu thực tế."""
    debt = _calculate_customer_debt(conn, customer_id)
    c = conn.cursor()
    c.execute("UPDATE customers SET current_debt = ? WHERE id = ?", (debt, customer_id))


def _sync_supplier_debt(conn, supplier_id: int):
    """Cập nhật bản tóm tắt current_debt cho nhà cung cấp từ dữ liệu phiếu thực tế."""
    debt = _calculate_supplier_debt(conn, supplier_id)
    c = conn.cursor()
    c.execute("UPDATE suppliers SET current_debt = ? WHERE id = ?", (debt, supplier_id))


# ===================== TỔNG QUAN CÔNG NỢ =====================

@router.get("/debt/customers")
async def debt_customers_summary(request: Request):
    """Tổng quan công nợ khách hàng"""
    user = get_current_user(request)
    if not user or not check_permission(user, 'customers', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền xem công nợ")

    conn = get_db()
    c = conn.cursor()
    try:
        # Lấy hạn mức toàn cục từ settings
        c.execute("SELECT kh_debt_limit FROM settings WHERE id=1")
        srow = c.fetchone()
        kh_limit = float(srow[0] or 0) if srow else 0

        c.execute("""
            SELECT c.id, c.code, c.name, c.phone, c.address, c.customer_type,
                   c.current_debt
            FROM customers c
            WHERE c.is_active = 1
            ORDER BY c.current_debt DESC
        """)
        items = [dict(row) for row in c.fetchall()]

        for item in items:
            item['debt_limit'] = kh_limit
            debt_value = _calculate_customer_debt(conn, item['id'])
            item['current_debt'] = debt_value
            item['is_over_limit'] = 1 if (kh_limit > 0 and debt_value > kh_limit) else 0
            c.execute("UPDATE customers SET current_debt = ? WHERE id = ?", (debt_value, item['id']))

        total_debt = sum(float(x['current_debt'] or 0) for x in items)
        over_limit_count = sum(1 for x in items if x['is_over_limit'])

        conn.commit()

        return {
            "items": items,
            "total_debt": round(total_debt, 2),
            "total_credit": round(kh_limit * len(items), 2),
            "over_limit_count": over_limit_count,
            "count": len(items)
        }
    finally:
        conn.close()


@router.get("/debt/suppliers")
async def debt_suppliers_summary(request: Request):
    """Tổng quan công nợ nhà cung cấp"""
    user = get_current_user(request)
    if not user or not check_permission(user, 'suppliers', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền xem công nợ")

    conn = get_db()
    c = conn.cursor()
    try:
        # Lấy hạn mức toàn cục từ settings
        c.execute("SELECT ncc_debt_limit FROM settings WHERE id=1")
        srow = c.fetchone()
        ncc_limit = float(srow[0] or 0) if srow else 0

        c.execute("""
            SELECT s.id, s.code, s.name, s.phone, s.address, s.payment_terms,
                   s.current_debt
            FROM suppliers s
            WHERE s.is_active = 1
            ORDER BY s.current_debt DESC
        """)
        items = [dict(row) for row in c.fetchall()]

        for item in items:
            item['debt_limit'] = ncc_limit
            debt_value = _calculate_supplier_debt(conn, item['id'])
            item['current_debt'] = debt_value
            item['is_over_limit'] = 1 if (ncc_limit > 0 and debt_value > ncc_limit) else 0
            c.execute("UPDATE suppliers SET current_debt = ? WHERE id = ?", (debt_value, item['id']))

        total_debt = sum(float(x['current_debt'] or 0) for x in items)
        over_limit_count = sum(1 for x in items if x['is_over_limit'])

        conn.commit()

        return {
            "items": items,
            "total_debt": round(total_debt, 2),
            "total_credit": round(ncc_limit * len(items), 2),
            "over_limit_count": over_limit_count,
            "count": len(items)
        }
    finally:
        conn.close()


# ===================== CHI TIẾT CÔNG NỢ =====================

@router.get("/debt/customers/{customer_id}")
async def debt_customer_detail(customer_id: int, request: Request):
    """Chi tiết công nợ của một khách hàng"""
    user = get_current_user(request)
    if not user or not check_permission(user, 'customers', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền xem công nợ")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM customers WHERE id = ? AND is_active = 1", (customer_id,))
        customer = c.fetchone()
        if not customer:
            raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng")

        customer_current_debt = _calculate_customer_debt(conn, customer_id)
        c.execute("UPDATE customers SET current_debt = ? WHERE id = ?", (customer_current_debt, customer_id))

        # Lấy các đơn hàng chưa thanh toán hết
        c.execute("""
            SELECT eo.id, eo.code, eo.order_date, eo.final_amount, eo.paid_amount,
                   (eo.final_amount - eo.paid_amount) as remaining_debt,
                   eo.status, eo.payment_status
            FROM export_orders eo
            WHERE eo.customer_id = ? AND eo.status IN ('completed', 'shipped')
            ORDER BY eo.order_date DESC
        """, (customer_id,))
        orders = [dict(row) for row in c.fetchall()]

        # Lấy lịch sử thanh toán
        c.execute("""
            SELECT dp.*, eo.code as order_code
            FROM debt_payments dp
            LEFT JOIN export_orders eo ON dp.order_id = eo.id
            WHERE dp.partner_type = 'customer' AND dp.partner_id = ?
            ORDER BY dp.payment_date DESC
            LIMIT 100
        """, (customer_id,))
        payments = [dict(row) for row in c.fetchall()]

        total_debt = sum(float(o['remaining_debt'] or 0) for o in orders)
        customer_dict = dict(customer)
        customer_dict['current_debt'] = round(customer_current_debt, 2)

        return {
            "customer": customer_dict,
            "orders": orders,
            "payments": payments,
            "total_debt": round(total_debt, 2)
        }
    finally:
        conn.close()


@router.get("/debt/suppliers/{supplier_id}")
async def debt_supplier_detail(supplier_id: int, request: Request):
    """Chi tiết công nợ của một nhà cung cấp"""
    user = get_current_user(request)
    if not user or not check_permission(user, 'suppliers', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền xem công nợ")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM suppliers WHERE id = ? AND is_active = 1", (supplier_id,))
        supplier = c.fetchone()
        if not supplier:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhà cung cấp")

        supplier_current_debt = _calculate_supplier_debt(conn, supplier_id)
        c.execute("UPDATE suppliers SET current_debt = ? WHERE id = ?", (supplier_current_debt, supplier_id))

        # Lấy các đơn nhập chưa thanh toán hết
        c.execute("""
            SELECT io.id, io.code, io.order_date, io.final_amount, io.paid_amount,
                   (io.final_amount - io.paid_amount) as remaining_debt,
                   io.status, io.payment_status
            FROM import_orders io
            WHERE io.supplier_id = ? AND io.status = 'completed'
            ORDER BY io.order_date DESC
        """, (supplier_id,))
        orders = [dict(row) for row in c.fetchall()]

        # Lấy lịch sử thanh toán
        c.execute("""
            SELECT dp.*, io.code as order_code
            FROM debt_payments dp
            LEFT JOIN import_orders io ON dp.order_id = io.id
            WHERE dp.partner_type = 'supplier' AND dp.partner_id = ?
            ORDER BY dp.payment_date DESC
            LIMIT 100
        """, (supplier_id,))
        payments = [dict(row) for row in c.fetchall()]

        total_debt = sum(float(o['remaining_debt'] or 0) for o in orders)
        supplier_dict = dict(supplier)
        supplier_dict['current_debt'] = round(supplier_current_debt, 2)

        return {
            "supplier": supplier_dict,
            "orders": orders,
            "payments": payments,
            "total_debt": round(total_debt, 2)
        }
    finally:
        conn.close()


# ===================== THANH TOÁN =====================

@router.post("/debt/payment")
async def record_payment(data: PaymentCreate, request: Request):
    """Ghi nhận thanh toán công nợ"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Số tiền thanh toán phải lớn hơn 0")

    if data.partner_type not in ('customer', 'supplier'):
        raise HTTPException(status_code=400, detail="Loại đối tác không hợp lệ")

    if data.order_type not in ('import_order', 'export_order'):
        raise HTTPException(status_code=400, detail="Loại đơn hàng không hợp lệ")

    payment_date_norm = normalize_date_yyyy_mm_dd(data.payment_date) or normalize_date_yyyy_mm_dd(datetime.now())

    conn = get_db()
    c = conn.cursor()
    try:
        # ===================== VALIDATE HẠN MỨC CÔNG NỢ =====================
        c.execute("SELECT ncc_debt_limit, kh_debt_limit FROM settings WHERE id=1")
        srow = c.fetchone()
        ncc_limit = float(srow[0] or 0) if srow else 0
        kh_limit = float(srow[1] or 0) if srow else 0

        if data.partner_type == 'customer':
            current_debt = _calculate_customer_debt(conn, data.partner_id)
            new_debt = current_debt - data.amount
            if kh_limit > 0 and new_debt > kh_limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Công nợ khách hàng vượt hạn mức sau khi thanh toán ({new_debt:,.2f} > {kh_limit:,.2f})."
                )
        else:
            current_debt = _calculate_supplier_debt(conn, data.partner_id)
            new_debt = current_debt - data.amount
            if ncc_limit > 0 and new_debt > ncc_limit:
                raise HTTPException(
                    status_code=400,
                    detail=f"Công nợ nhà cung cấp vượt hạn mức sau khi thanh toán ({new_debt:,.2f} > {ncc_limit:,.2f})."
                )

        # Ghi nhận thanh toán
        c.execute("""
            INSERT INTO debt_payments 
            (partner_type, partner_id, order_type, order_id, payment_date, 
             amount, payment_method, reference_number, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data.partner_type, data.partner_id, data.order_type, data.order_id,
              payment_date_norm, data.amount, data.payment_method, data.reference_number,
              data.notes, user['id']))

        # Cập nhật paid_amount trên đơn hàng nếu có order_id
        if data.order_id:
            if data.order_type == 'export_order':
                c.execute("""
                    UPDATE export_orders 
                    SET paid_amount = paid_amount + ?,
                        payment_status = CASE 
                            WHEN paid_amount + ? >= final_amount THEN 'paid'
                            WHEN paid_amount + ? > 0 THEN 'partial'
                            ELSE payment_status
                        END
                    WHERE id = ?
                """, (data.amount, data.amount, data.amount, data.order_id))
            elif data.order_type == 'import_order':
                c.execute("""
                    UPDATE import_orders 
                    SET paid_amount = paid_amount + ?,
                        payment_status = CASE 
                            WHEN paid_amount + ? >= final_amount THEN 'paid'
                            WHEN paid_amount + ? > 0 THEN 'partial'
                            ELSE payment_status
                        END
                    WHERE id = ?
                """, (data.amount, data.amount, data.amount, data.order_id))

        # Đồng bộ current_debt
        if data.partner_type == 'customer':
            _sync_customer_debt(conn, data.partner_id)
        else:
            _sync_supplier_debt(conn, data.partner_id)

        conn.commit()
        return {"message": "Ghi nhận thanh toán thành công", "payment_id": c.lastrowid}

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/debt/batch-payment")
async def record_batch_payment(data: BatchPaymentCreate, request: Request):
    """Ghi nhận thanh toán hàng loạt cho nhiều phiếu"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    if data.partner_type not in ('customer', 'supplier'):
        raise HTTPException(status_code=400, detail="Loại đối tác không hợp lệ")

    if data.order_type not in ('import_order', 'export_order'):
        raise HTTPException(status_code=400, detail="Loại đơn hàng không hợp lệ")

    if not data.payments or len(data.payments) == 0:
        raise HTTPException(status_code=400, detail="Phải có ít nhất 1 khoản thanh toán")

    total_amount = sum(p.amount for p in data.payments if p.amount > 0)
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Tổng số tiền thanh toán phải lớn hơn 0")

    payment_date_norm = normalize_date_yyyy_mm_dd(data.payment_date) or normalize_date_yyyy_mm_dd(datetime.now())

    conn = get_db()
    c = conn.cursor()
    try:
        # Validate hạn mức công nợ
        c.execute("SELECT ncc_debt_limit, kh_debt_limit FROM settings WHERE id=1")
        srow = c.fetchone()
        ncc_limit = float(srow[0] or 0) if srow else 0
        kh_limit = float(srow[1] or 0) if srow else 0

        # Kiểm tra tổng nợ hiện tại
        if data.partner_type == 'customer':
            current_debt = _calculate_customer_debt(conn, data.partner_id)
            new_debt = current_debt - total_amount
            if kh_limit > 0 and new_debt > kh_limit:
                raise HTTPException(status_code=400, detail="Công nợ khách hàng vượt hạn mức sau thanh toán")
        else:
            current_debt = _calculate_supplier_debt(conn, data.partner_id)
            new_debt = current_debt - total_amount
            if ncc_limit > 0 and new_debt > ncc_limit:
                raise HTTPException(status_code=400, detail="Công nợ nhà cung cấp vượt hạn mức sau thanh toán")

        # Ghi nhận từng thanh toán
        payment_ids = []
        for payment in data.payments:
            if payment.amount <= 0:
                continue
            c.execute("""
                INSERT INTO debt_payments 
                (partner_type, partner_id, order_type, order_id, payment_date, 
                 amount, payment_method, reference_number, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data.partner_type, data.partner_id, data.order_type, payment.order_id,
                  payment_date_norm, payment.amount, data.payment_method, data.reference_number,
                  data.notes, user['id']))
            payment_id = c.lastrowid
            payment_ids.append(payment_id)

            # Cập nhật paid_amount trên đơn hàng
            if data.order_type == 'export_order':
                c.execute("""
                    UPDATE export_orders 
                    SET paid_amount = paid_amount + ?,
                        payment_status = CASE 
                            WHEN paid_amount + ? >= final_amount THEN 'paid'
                            WHEN paid_amount + ? > 0 THEN 'partial'
                            ELSE payment_status
                        END
                    WHERE id = ?
                """, (payment.amount, payment.amount, payment.amount, payment.order_id))
            elif data.order_type == 'import_order':
                c.execute("""
                    UPDATE import_orders 
                    SET paid_amount = paid_amount + ?,
                        payment_status = CASE 
                            WHEN paid_amount + ? >= final_amount THEN 'paid'
                            WHEN paid_amount + ? > 0 THEN 'partial'
                            ELSE payment_status
                        END
                    WHERE id = ?
                """, (payment.amount, payment.amount, payment.amount, payment.order_id))

        # Đồng bộ current_debt
        if data.partner_type == 'customer':
            _sync_customer_debt(conn, data.partner_id)
        else:
            _sync_supplier_debt(conn, data.partner_id)

        conn.commit()
        return {
            "message": "Ghi nhận thanh toán hàng loạt thành công",
            "payment_ids": payment_ids,
            "total_amount": round(total_amount, 2)
        }

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ===================== TÍNH LẠI CÔNG NỢ =====================

@router.post("/debt/customers/{customer_id}/recalculate")
async def recalculate_customer_debt(customer_id: int, request: Request):
    """Tính toán lại công nợ cho khách hàng"""
    user = get_current_user(request)
    if not user or user.get('role') not in ('admin', 'manager'):
        raise HTTPException(status_code=403, detail="Chỉ admin/manager mới có quyền này")

    conn = get_db()
    try:
        _sync_customer_debt(conn, customer_id)
        conn.commit()

        c = conn.cursor()
        c.execute("SELECT current_debt FROM customers WHERE id = ?", (customer_id,))
        debt = c.fetchone()[0] or 0
        return {"message": "Đã tính lại công nợ", "current_debt": round(debt, 2)}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/debt/suppliers/{supplier_id}/recalculate")
async def recalculate_supplier_debt(supplier_id: int, request: Request):
    """Tính toán lại công nợ cho nhà cung cấp"""
    user = get_current_user(request)
    if not user or user.get('role') not in ('admin', 'manager'):
        raise HTTPException(status_code=403, detail="Chỉ admin/manager mới có quyền này")

    conn = get_db()
    try:
        _sync_supplier_debt(conn, supplier_id)
        conn.commit()

        c = conn.cursor()
        c.execute("SELECT current_debt FROM suppliers WHERE id = ?", (supplier_id,))
        debt = c.fetchone()[0] or 0
        return {"message": "Đã tính lại công nợ", "current_debt": round(debt, 2)}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ===================== LỊCH SỬ THANH TOÁN =====================

@router.get("/debt/payments")
async def list_payments(
    partner_type: Optional[str] = None,
    partner_id: Optional[int] = None,
    limit: int = 50,
    request: Request = None
):
    """Lấy lịch sử thanh toán"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    conn = get_db()
    c = conn.cursor()
    try:
        where_clauses = []
        params = []

        if partner_type:
            where_clauses.append("dp.partner_type = ?")
            params.append(partner_type)
        if partner_id is not None:
            where_clauses.append("dp.partner_id = ?")
            params.append(partner_id)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        c.execute(f"""
            SELECT dp.*, 
                   CASE 
                       WHEN dp.partner_type = 'customer' THEN c.name
                       WHEN dp.partner_type = 'supplier' THEN s.name
                   END as partner_name,
                   CASE 
                       WHEN dp.order_type = 'export_order' THEN eo.code
                       WHEN dp.order_type = 'import_order' THEN io.code
                   END as order_code
            FROM debt_payments dp
            LEFT JOIN customers c ON dp.partner_type = 'customer' AND dp.partner_id = c.id
            LEFT JOIN suppliers s ON dp.partner_type = 'supplier' AND dp.partner_id = s.id
            LEFT JOIN export_orders eo ON dp.order_type = 'export_order' AND dp.order_id = eo.id
            LEFT JOIN import_orders io ON dp.order_type = 'import_order' AND dp.order_id = io.id
            {where_sql}
            ORDER BY dp.created_at DESC
            LIMIT ?
        """, params + [limit])
        items = [dict(row) for row in c.fetchall()]
        return {"items": items, "count": len(items)}
    finally:
        conn.close()


# ===================== TRANG THANH TOÁN ẨN =====================

@router.get("/debt/payment-page")
async def debt_payment_page(request: Request):
    """Trang thanh toán công nợ - chỉ truy cập nội bộ"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    # Trang ẩn, không cần quyền đặc biệt, chỉ cần đăng nhập
    return render_debt_payment(request)


def render_debt_payment(request: Request):
    """Render trang thanh toán công nợ"""
    from fastapi.responses import HTMLResponse
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "debt_payment.html"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Trang thanh toán chưa được cấu hình")

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Inject context nếu cần (không dùng Jinja2 render trực tiếp ở đây vì không có env)
        html = content.replace("{{ request }}", str(request))
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi render trang: {str(e)}")


@router.get("/debt/orders-to-pay")
async def get_orders_to_pay(
    partner_type: str,
    partner_id: int,
    request: Request = None
):
    """Lấy danh sách đơn hàng còn nợ của đối tác để thanh toán"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    if partner_type not in ('customer', 'supplier'):
        raise HTTPException(status_code=400, detail="Loại đối tác không hợp lệ")

    conn = get_db()
    c = conn.cursor()
    try:
        # Lấy thông tin đối tác
        if partner_type == 'customer':
            c.execute("""
                SELECT id, code, name, phone, current_debt, credit_limit as debt_limit
                FROM customers
                WHERE id = ? AND is_active = 1
            """, (partner_id,))
        else:
            c.execute("""
                SELECT id, code, name, phone, current_debt, payment_terms
                FROM suppliers
                WHERE id = ? AND is_active = 1
            """, (partner_id,))

        partner = c.fetchone()
        if not partner:
            raise HTTPException(status_code=404, detail="Không tìm thấy đối tác")

        partner_info = dict(partner)

        # Lấy đơn hàng còn nợ
        if partner_type == 'customer':
            c.execute("""
                SELECT eo.id, eo.code, eo.order_date, eo.final_amount, eo.paid_amount,
                       (eo.final_amount - eo.paid_amount) as remaining_debt,
                       eo.status, eo.payment_status, 'export_order' as order_type
                FROM export_orders eo
                WHERE eo.customer_id = ? AND eo.status IN ('completed', 'shipped')
                  AND eo.paid_amount < eo.final_amount
                ORDER BY eo.order_date DESC
            """, (partner_id,))
        else:
            c.execute("""
                SELECT io.id, io.code, io.order_date, io.final_amount, io.paid_amount,
                       (io.final_amount - io.paid_amount) as remaining_debt,
                       io.status, io.payment_status, 'import_order' as order_type
                FROM import_orders io
                WHERE io.supplier_id = ? AND io.status = 'completed'
                  AND io.paid_amount < io.final_amount
                ORDER BY io.order_date DESC
            """, (partner_id,))

        orders = [dict(row) for row in c.fetchall()]
        total_debt = sum(float(o['remaining_debt'] or 0) for o in orders)

        return {
            "partner": partner_info,
            "orders": orders,
            "total_debt": round(total_debt, 2),
            "order_count": len(orders)
        }
    finally:
        conn.close()


@router.get("/debt/partners/search")
async def search_partners_for_debt(
    type: str = "all",
    keyword: str = "",
    request: Request = None
):
    """Tìm kiếm đối tác cho trang thanh toán"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    keyword = (keyword or "").strip()

    conn = get_db()
    c = conn.cursor()
    try:
        results = []

        if type in ("all", "customer"):
            query = """
                SELECT 'customer' as partner_type, id, code, name, phone, current_debt
                FROM customers
                WHERE is_active = 1 AND current_debt > 0
            """
            params = []
            if keyword:
                query += " AND (name LIKE ? OR code LIKE ?)"
                term = f"%{keyword}%"
                params.extend([term, term])
            query += " ORDER BY current_debt DESC LIMIT 50"

            c.execute(query, params)
            for row in c.fetchall():
                d = dict(row)
                d['code'] = d.get('code', '')
                d['name'] = d.get('name', '')
                d['phone'] = d.get('phone', '')
                results.append({
                    "partner_type": "customer",
                    "id": d['id'],
                    "code": d['code'],
                    "name": d['name'],
                    "phone": d.get('phone', ''),
                    "current_debt": round(float(d.get('current_debt') or 0), 2)
                })

        if type in ("all", "supplier"):
            query = """
                SELECT 'supplier' as partner_type, id, code, name, phone, current_debt
                FROM suppliers
                WHERE is_active = 1 AND current_debt > 0
            """
            params = []
            if keyword:
                query += " AND (name LIKE ? OR code LIKE ?)"
                term = f"%{keyword}%"
                params.extend([term, term])
            query += " ORDER BY current_debt DESC LIMIT 50"

            c.execute(query, params)
            for row in c.fetchall():
                d = dict(row)
                d['code'] = d.get('code', '')
                d['name'] = d.get('name', '')
                d['phone'] = d.get('phone', '')
                results.append({
                    "partner_type": "supplier",
                    "id": d['id'],
                    "code": d['code'],
                    "name": d['name'],
                    "phone": d.get('phone', ''),
                    "current_debt": round(float(d.get('current_debt') or 0), 2)
                })

        # Sắp xếp theo nợ giảm dần
        results.sort(key=lambda x: x['current_debt'], reverse=True)

        return {"items": results, "count": len(results)}
    finally:
        conn.close()