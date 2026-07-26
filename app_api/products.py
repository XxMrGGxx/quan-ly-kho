from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Optional
from database import get_db
from app_api.auth import get_current_user, get_warehouse_filter_clause


router = APIRouter()


class ProductCreate(BaseModel):
    code: Optional[str] = None
    barcode: Optional[str] = None
    name: str
    warehouse_id: int  # Bắt buộc chọn kho
    category_id: Optional[int] = None
    unit_id: Optional[int] = None
    description: Optional[str] = None
    specifications: Optional[str] = None
    min_stock: int = 5
    max_stock: int = 100
    cost_price: float = 0
    selling_price: float = 0
    discount_rate: float = 0

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Tên sản phẩm không được để trống')
        if len(v.strip()) > 200:
            raise ValueError('Tên sản phẩm không được quá 200 ký tự')
        return v.strip()

    @field_validator('code')
    @classmethod
    def validate_code(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 50:
                raise ValueError('Mã sản phẩm không được quá 50 ký tự')
        return v

    @field_validator('barcode')
    @classmethod
    def validate_barcode(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 100:
                raise ValueError('Barcode không được quá 100 ký tự')
        return v

    @field_validator('warehouse_id')
    @classmethod
    def validate_warehouse_id(cls, v):
        if v is None or v < 1:
            raise ValueError('Kho không hợp lệ')
        return v

    @field_validator('min_stock', 'max_stock')
    @classmethod
    def validate_stock(cls, v):
        if v is not None and v < 0:
            raise ValueError('Giá trị tồn kho không được âm')
        return v

    @field_validator('cost_price', 'selling_price', 'discount_rate')
    @classmethod
    def validate_price(cls, v):
        if v is not None and v < 0:
            raise ValueError('Giá trị không được âm')
        return v

    @model_validator(mode='after')
    def validate_discount_rate(self):
        if self.discount_rate > 100:
            raise ValueError('Chiết khấu không được vượt quá 100%')
        return self

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    barcode: Optional[str] = None
    warehouse_id: Optional[int] = None  # Cho phép thay đổi kho
    category_id: Optional[int] = None
    unit_id: Optional[int] = None
    description: Optional[str] = None
    specifications: Optional[str] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    discount_rate: Optional[float] = None
    is_active: Optional[int] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 200:
                raise ValueError('Tên sản phẩm không được quá 200 ký tự')
        return v

    @field_validator('barcode')
    @classmethod
    def validate_barcode(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) > 100:
                raise ValueError('Barcode không được quá 100 ký tự')
        return v

    @field_validator('cost_price', 'selling_price', 'discount_rate')
    @classmethod
    def validate_price(cls, v):
        if v is not None and v < 0:
            raise ValueError('Giá trị không được âm')
        return v

    @field_validator('min_stock', 'max_stock')
    @classmethod
    def validate_stock(cls, v):
        if v is not None and v < 0:
            raise ValueError('Giá trị tồn kho không được âm')
        return v

# ========== PRODUCTS CRUD ==========

@router.get("")
async def list_products(
    request: Request,
    search: str = Query("", description="Từ khóa tìm kiếm"),
    limit: int = Query(20, description="Số lượng bản ghi"),
    offset: int = Query(0, description="Vị trí bắt đầu")
):
    """Lấy danh sách sản phẩm với tìm kiếm realtime"""
    user = get_current_user(request)
    wh_clause, wh_params = get_warehouse_filter_clause(user, 'p.warehouse_id')
    
    conn = get_db()
    c = conn.cursor()
    
    # Count query
    count_query = f"SELECT COUNT(*) FROM products p WHERE p.is_active = 1 {wh_clause}"
    count_params = wh_params[:]
    
    # Data query
    data_query = f"""
        SELECT p.*, u.name as unit_name, c.name as category_name,
               COALESCE(i.quantity_in_stock, 0) as stock, w.name as warehouse_name
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN inventory i ON p.id = i.product_id AND i.warehouse_id = p.warehouse_id
        LEFT JOIN warehouses w ON p.warehouse_id = w.id
        WHERE p.is_active = 1 {wh_clause}
    """
    params = wh_params[:]
    
    if search and search.strip():
        search_condition = " AND (p.name LIKE ? OR p.code LIKE ? OR p.barcode LIKE ?)"
        term = f"%{search}%"
        count_query += search_condition
        data_query += search_condition
        count_params.extend([term, term, term])
        params.extend([term, term, term])
    
    # Get total count
    c.execute(count_query, count_params)
    total = c.fetchone()[0]
    
    # Get data with pagination
    data_query += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    c.execute(data_query, params)
    items = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.post("")
async def create_product(product: ProductCreate):
    """Tạo sản phẩm mới"""
    conn = get_db()
    c = conn.cursor()
    
    # Tự động sinh mã nếu chưa có
    if not product.code:
        year = datetime.now().strftime("%Y")
        # Use MAX() to get the highest existing code number, then increment
        # This handles gaps in sequence correctly
        c.execute(f"SELECT MAX(CAST(SUBSTR(code, 4) AS INTEGER)) FROM products WHERE code LIKE 'SP{year}%'")
        max_num = c.fetchone()[0]
        next_num = (max_num or 0) + 1
        product.code = f"SP{year}{next_num:04d}"
    
    # Kiểm tra mã đã tồn tại chưa
    c.execute("SELECT id FROM products WHERE code = ?", (product.code,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Mã sản phẩm {product.code} đã tồn tại")
    
    # Kiểm tra barcode nếu có
    if product.barcode:
        c.execute("SELECT id FROM products WHERE barcode = ?", (product.barcode,))
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"Barcode {product.barcode} đã tồn tại")
    
    # Kiểm tra warehouse_id có tồn tại không
    c.execute("SELECT id FROM warehouses WHERE id = ? AND is_active = 1", (product.warehouse_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Kho không hợp lệ hoặc không tồn tại")
    
    # ✅ KIỂM TRA: Sản phẩm không được phép ở nhiều kho cùng lúc
    # Nếu sản phẩm đã có inventory record trong kho khác -> chặn
    c.execute("""
        SELECT i.warehouse_id, w.name as warehouse_name
        FROM inventory i
        JOIN warehouses w ON i.warehouse_id = w.id
        WHERE i.product_id IN (
            SELECT id FROM products WHERE barcode = ? OR code = ?
        ) AND i.warehouse_id != ?
    """, (product.barcode, product.code, product.warehouse_id))
    existing_in_other_warehouses = c.fetchall()
    if existing_in_other_warehouses:
        wh_names = ", ".join([row['warehouse_name'] for row in existing_in_other_warehouses])
        conn.close()
        raise HTTPException(
            status_code=400, 
            detail=f"Sản phẩm đã tồn tại trong kho: {wh_names}. Một sản phẩm chỉ được phép ở một kho duy nhất."
        )
    
    try:
        c.execute("""
            INSERT INTO products (
                code, barcode, name, warehouse_id, category_id, unit_id, description, 
                specifications, min_stock, max_stock, cost_price, selling_price, discount_rate,
                created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            product.code, product.barcode, product.name, product.warehouse_id,
            product.category_id, product.unit_id, product.description, product.specifications,
            product.min_stock, product.max_stock, round(product.cost_price, 2), round(product.selling_price, 2),
            round(product.discount_rate, 2),
            datetime.now().isoformat()
        ))
        conn.commit()
        
        product_id = c.lastrowid
        
        # Khởi tạo inventory cho warehouse của sản phẩm
        c.execute("""
            INSERT OR IGNORE INTO inventory (product_id, warehouse_id, quantity_in_stock, updated_at)
            VALUES (?, ?, 0, ?)
        """, (product_id, product.warehouse_id, datetime.now().isoformat()))
        conn.commit()
        
        conn.close()
        return {
            "id": product_id, 
            "code": product.code, 
            "message": "Thêm sản phẩm thành công"
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Lỗi: {str(e)}")


@router.put("/{product_id}")
async def update_product(product_id: int, product: ProductUpdate):
    """Cập nhật sản phẩm"""
    conn = get_db()
    c = conn.cursor()
    
    # Kiểm tra sản phẩm tồn tại
    c.execute("SELECT id, code, barcode, warehouse_id FROM products WHERE id = ?", (product_id,))
    existing_product = c.fetchone()
    if not existing_product:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    existing_product = dict(existing_product)
    
    # Xây dựng câu lệnh UPDATE
    updates = []
    params = []
    
    if product.name is not None:
        updates.append("name=?")
        params.append(product.name)
    if product.barcode is not None:
        updates.append("barcode=?")
        params.append(product.barcode)
    if product.category_id is not None:
        updates.append("category_id=?")
        params.append(product.category_id)
    if product.unit_id is not None:
        updates.append("unit_id=?")
        params.append(product.unit_id)
    if product.description is not None:
        updates.append("description=?")
        params.append(product.description)
    if product.specifications is not None:
        updates.append("specifications=?")
        params.append(product.specifications)
    if product.min_stock is not None:
        updates.append("min_stock=?")
        params.append(product.min_stock)
    if product.max_stock is not None:
        updates.append("max_stock=?")
        params.append(product.max_stock)
    if product.warehouse_id is not None:
        # Kiểm tra warehouse_id có tồn tại không
        c.execute("SELECT id FROM warehouses WHERE id = ? AND is_active = 1", (product.warehouse_id,))
        if not c.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Kho không hợp lệ hoặc không tồn tại")
        
        # ✅ KIỂM TRA: Sản phẩm không được phép ở nhiều kho cùng lúc
        # Nếu đổi warehouse, kiểm tra xem sản phẩm đã có inventory trong kho khác chưa
        if product.warehouse_id != existing_product['warehouse_id']:
            c.execute("""
                SELECT i.warehouse_id, w.name as warehouse_name
                FROM inventory i
                JOIN warehouses w ON i.warehouse_id = w.id
                WHERE i.product_id = ? AND i.warehouse_id != ?
                LIMIT 1
            """, (product_id, product.warehouse_id))
            existing_in_other = c.fetchone()
            if existing_in_other:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail=f"Sản phẩm đã tồn tại trong kho '{existing_in_other['warehouse_name']}'. Một sản phẩm chỉ được phép ở một kho duy nhất. Vui lòng xóa sản phẩm khỏi kho cũ trước khi chuyển sang kho mới."
                )
        
        updates.append("warehouse_id=?")
        params.append(product.warehouse_id)
    if product.cost_price is not None:
        updates.append("cost_price=?")
        params.append(round(product.cost_price, 2))
    if product.selling_price is not None:
        updates.append("selling_price=?")
        params.append(round(product.selling_price, 2))
    if product.discount_rate is not None:
        updates.append("discount_rate=?")
        params.append(round(product.discount_rate, 2))
    if product.is_active is not None:
        updates.append("is_active=?")
        params.append(product.is_active)
    
    updates.append("updated_at=?")
    params.append(datetime.now().isoformat())
    
    if updates:
        params.append(product_id)
        query = f"UPDATE products SET {', '.join(updates)} WHERE id=?"
        c.execute(query, params)
        conn.commit()
    
    conn.close()
    return {"message": "Cập nhật sản phẩm thành công"}

@router.delete("/{product_id}")
async def delete_product(product_id: int):
    """Xóa sản phẩm (vô hiệu hóa)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE products SET is_active=0 WHERE id=?", (product_id,))
    conn.commit()
    conn.close()
    return {"message": "Đã xóa sản phẩm"}

# ========== CATEGORIES ==========

@router.get("/categories")
async def list_categories(
    search: str = Query("", description="Từ khóa tìm kiếm"),
    limit: int = Query(20, description="Số lượng bản ghi"),
    offset: int = Query(0, description="Vị trí bắt đầu")
):
    """Lấy danh sách danh mục với phân trang"""
    conn = get_db()
    c = conn.cursor()
    
    count_query = "SELECT COUNT(*) FROM categories WHERE is_active=1"
    data_query = "SELECT id, code, name, parent_id, description FROM categories WHERE is_active=1"
    params = []
    
    if search and search.strip():
        search_condition = " AND (name LIKE ? OR code LIKE ?)"
        term = f"%{search}%"
        count_query += search_condition
        data_query += search_condition
        params.extend([term, term])
    
    c.execute(count_query, params)
    total = c.fetchone()[0]
    
    data_query += " ORDER BY name LIMIT ? OFFSET ?"
    list_params = params + [limit, offset]
    c.execute(data_query, list_params)
    items = [dict(row) for row in c.fetchall()]
    
    # Lấy tên parent cho mỗi category
    for item in items:
        if item['parent_id']:
            c.execute("SELECT name FROM categories WHERE id=?", (item['parent_id'],))
            parent = c.fetchone()
            item['parent_name'] = parent['name'] if parent else ''
        else:
            item['parent_name'] = ''
    
    conn.close()
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/categories/all")
async def get_categories_all():
    """Lấy tất cả danh mục (không phân trang)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, code, name, parent_id, description FROM categories WHERE is_active=1 ORDER BY name")
    categories = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": categories}

@router.put("/categories/{cat_id}")
async def update_category(cat_id: int, data: dict):
    """Cập nhật danh mục"""
    conn = get_db()
    c = conn.cursor()
    updates = []
    params = []
    for field in ['name', 'code', 'parent_id', 'description', 'is_active']:
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])
    if not updates:
        conn.close()
        return {"message": "Không có gì thay đổi"}
    params.append(cat_id)
    try:
        c.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
        return {"message": "Cập nhật thành công"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int):
    """Xóa danh mục (vô hiệu hóa)"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE categories SET is_active=0 WHERE id=?", (cat_id,))
        conn.commit()
        return {"message": "Đã xóa danh mục"}
    finally:
        conn.close()

@router.post("/categories")
async def create_category(data: dict):
    """Tạo danh mục mới"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO categories (code, name, parent_id, description)
            VALUES (?, ?, ?, ?)
        """, (data.get('code'), data.get('name'), data.get('parent_id'), data.get('description')))
        conn.commit()
        return {"id": c.lastrowid, "message": "Thêm danh mục thành công"}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# ========== UNITS ==========

@router.get("/units")
async def list_units(
    search: str = Query("", description="Từ khóa tìm kiếm"),
    limit: int = Query(20, description="Số lượng bản ghi"),
    offset: int = Query(0, description="Vị trí bắt đầu")
):
    """Lấy danh sách đơn vị tính với phân trang"""
    conn = get_db()
    c = conn.cursor()
    
    count_query = "SELECT COUNT(*) FROM units"
    data_query = "SELECT id, code, name, description FROM units"
    params = []
    
    if search and search.strip():
        search_condition = " WHERE (name LIKE ? OR code LIKE ?)"
        term = f"%{search}%"
        count_query += search_condition
        data_query += search_condition
        params.extend([term, term])
    
    c.execute(count_query, params)
    total = c.fetchone()[0]
    
    data_query += " ORDER BY name LIMIT ? OFFSET ?"
    list_params = params + [limit, offset]
    c.execute(data_query, list_params)
    items = [dict(row) for row in c.fetchall()]
    
    conn.close()
    return {"items": items, "total": total, "limit": limit, "offset": offset}

@router.get("/units/all")
async def get_units_all():
    """Lấy tất cả đơn vị tính (không phân trang)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, code, name, description FROM units ORDER BY name")
    units = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": units}

@router.post("/units")
async def create_unit(data: dict):
    """Tạo đơn vị tính mới"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO units (code, name, description)
            VALUES (?, ?, ?)
        """, (data.get('code'), data.get('name'), data.get('description')))
        conn.commit()
        return {"id": c.lastrowid, "message": "Thêm đơn vị thành công"}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.put("/units/{unit_id}")
async def update_unit(unit_id: int, data: dict):
    """Cập nhật đơn vị tính"""
    conn = get_db()
    c = conn.cursor()
    updates = []
    params = []
    for field in ['name', 'code', 'description']:
        if field in data:
            updates.append(f"{field}=?")
            params.append(data[field])
    params.append(unit_id)
    try:
        c.execute(f"UPDATE units SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
        return {"message": "Cập nhật thành công"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/units/{unit_id}")
async def delete_unit(unit_id: int):
    """Xóa đơn vị tính"""
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM units WHERE id=?", (unit_id,))
        conn.commit()
        return {"message": "Đã xóa đơn vị tính"}
    finally:
        conn.close()

# Route động phải đứng SAU route tĩnh để FastAPI không nhầm
@router.get("/categories/{cat_id}")
async def get_category(cat_id: int):
    """Lấy chi tiết 1 danh mục"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, code, name, parent_id, description FROM categories WHERE id=?", (cat_id,))
    cat = c.fetchone()
    conn.close()
    if not cat:
        raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    return dict(cat)

@router.get("/units/{unit_id}")
async def get_unit(unit_id: int):
    """Lấy chi tiết 1 đơn vị tính"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, code, name, description FROM units WHERE id=?", (unit_id,))
    unit = c.fetchone()
    conn.close()
    if not unit:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn vị tính")
    return dict(unit)

@router.get("/{product_id}")
async def get_product(product_id: int):
    """Lấy chi tiết sản phẩm"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT p.*, u.name as unit_name, c.name as category_name, w.name as warehouse_name
        FROM products p
        LEFT JOIN units u ON p.unit_id = u.id
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN warehouses w ON p.warehouse_id = w.id
        WHERE p.id = ?
    """, (product_id,))
    product = c.fetchone()
    conn.close()
    
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    
    return dict(product)
