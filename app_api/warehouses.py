from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from database import get_db
from .auth import get_current_user, check_permission, get_warehouse_filter_clause

router = APIRouter()

class WarehouseCreate(BaseModel):
    code: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None

class LocationCreate(BaseModel):
    zone_id: int
    code: str
    name: str
    rack: Optional[str] = None
    shelf: Optional[str] = None
    bin: Optional[str] = None

@router.get("")
async def list_warehouses(request: Request = None):
    user = get_current_user(request)
    wh_clause, wh_params = get_warehouse_filter_clause(user, 'w.id')
    
    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT * FROM warehouses WHERE is_active=1 {wh_clause}", wh_params)
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": items}

@router.post("")
async def create_warehouse(data: WarehouseCreate, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'settings', 'create'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Kiểm tra nếu mã kho đã tồn tại nhưng bị xóa mềm (is_active=0)
        c.execute("SELECT id, is_active FROM warehouses WHERE code=?", (data.code,))
        existing = c.fetchone()
        if existing:
            if existing['is_active'] == 0:
                # Kho đã bị xóa mềm -> kích hoạt lại và cập nhật thông tin
                c.execute("""
                    UPDATE warehouses 
                    SET name=?, address=?, phone=?, is_active=1
                    WHERE id=?
                """, (data.name, data.address, data.phone, existing['id']))
                conn.commit()
                return {"id": existing['id'], "message": "Đã khôi phục kho từ bản ghi đã xóa"}
            else:
                raise HTTPException(status_code=400, detail=f"Mã kho '{data.code}' đã tồn tại")
        
        c.execute("INSERT INTO warehouses (code, name, address, phone) VALUES (?, ?, ?, ?)",
                  (data.code, data.name, data.address, data.phone))
        conn.commit()
        return {"id": c.lastrowid, "message": "Thêm kho thành công"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.put("/{wh_id}")
async def update_warehouse(wh_id: int, data: WarehouseCreate, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'settings', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE warehouses 
            SET code=?, name=?, address=?, phone=?
            WHERE id=?
        """, (data.code, data.name, data.address, data.phone, wh_id))
        conn.commit()
        return {"message": "Cập nhật kho thành công"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/{wh_id}")
async def delete_warehouse(wh_id: int, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'settings', 'delete'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    try:
        # Vô hiệu hóa thay vì xóa cứng để bảo toàn lịch sử
        c.execute("UPDATE warehouses SET is_active=0 WHERE id=?", (wh_id,))
        conn.commit()
        return {"message": "Đã xóa kho"}
    finally:
        conn.close()

@router.get("/zones/{wh_id}")
async def get_zones(wh_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM warehouse_zones WHERE warehouse_id=?", (wh_id,))
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": items}

@router.post("/zones")
async def create_zone(wh_id: int, code: str, name: str, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'settings', 'create'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO warehouse_zones (warehouse_id, code, name) VALUES (?, ?, ?)",
                  (wh_id, code, name))
        conn.commit()
        return {"id": c.lastrowid, "message": "Thêm khu vực thành công"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.get("/locations/{zone_id}")
async def get_locations(zone_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM warehouse_locations WHERE zone_id=? AND is_active=1", (zone_id,))
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": items}

@router.post("/locations")
async def create_location(data: LocationCreate, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'inventory', 'create'):
        raise HTTPException(status_code=403, detail="Không có quyền")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO warehouse_locations (zone_id, code, name, rack, shelf, bin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (data.zone_id, data.code, data.name, data.rack, data.shelf, data.bin))
        conn.commit()
        return {"id": c.lastrowid, "message": "Thêm vị trí thành công"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.put("/locations/{loc_id}")
async def update_location(loc_id: int, data: LocationCreate, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'inventory', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE warehouse_locations 
            SET code=?, name=?, rack=?, shelf=?, bin=?
            WHERE id=?
        """, (data.code, data.name, data.rack, data.shelf, data.bin, loc_id))
        conn.commit()
        return {"message": "Cập nhật vị trí thành công"}
    finally:
        conn.close()

@router.delete("/locations/{loc_id}")
async def delete_location(loc_id: int, request: Request):
    user = get_current_user(request)
    if not check_permission(user, 'inventory', 'delete'):
        raise HTTPException(status_code=403, detail="Không có quyền")

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE warehouse_locations SET is_active=0 WHERE id=?", (loc_id,))
        conn.commit()
        return {"message": "Đã xóa vị trí"}
    finally:
        conn.close()

@router.get("/product-stock-locations/{product_id}")
async def get_product_locations(product_id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT pl.*, wl.name as location_name, wz.name as zone_name, w.name as warehouse_name
        FROM product_locations pl
        JOIN warehouse_locations wl ON pl.location_id = wl.id
        JOIN warehouse_zones wz ON wl.zone_id = wz.id
        JOIN warehouses w ON wz.warehouse_id = w.id
        WHERE pl.product_id = ?
    """, (product_id,))
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": items}


# ========== QUẢN LÝ GÁN KHO CHO NGƯỜI DÙNG ==========

@router.get("/user-assignments/{user_id}")
async def get_user_warehouse_assignments(user_id: int, request: Request):
    user = get_current_user(request)
    if not user or not check_permission(user, 'users', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT uw.id, uw.warehouse_id, w.code, w.name, w.address, uw.created_at
        FROM user_warehouses uw
        JOIN warehouses w ON uw.warehouse_id = w.id
        WHERE uw.user_id = ? AND w.is_active = 1
        ORDER BY w.name
    """, (user_id,))
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"items": items}


@router.post("/user-assignments")
async def assign_user_warehouses(data: dict, request: Request):
    user = get_current_user(request)
    if not user or not check_permission(user, 'users', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    target_user_id = data.get('user_id')
    warehouse_ids = data.get('warehouse_ids', [])
    
    if not target_user_id:
        raise HTTPException(status_code=400, detail="Thiếu user_id")
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM user_warehouses WHERE user_id = ?", (target_user_id,))
        for wh_id in warehouse_ids:
            c.execute("INSERT OR IGNORE INTO user_warehouses (user_id, warehouse_id) VALUES (?, ?)",
                      (target_user_id, wh_id))
        conn.commit()
        return {"message": "Đã cập nhật kho cho người dùng"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.delete("/user-assignments/{user_id}")
async def remove_user_warehouse_assignment(user_id: int, warehouse_id: int, request: Request):
    user = get_current_user(request)
    if not user or not check_permission(user, 'users', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM user_warehouses WHERE user_id = ? AND warehouse_id = ?",
                  (user_id, warehouse_id))
        conn.commit()
        return {"message": "Đã xóa gán kho"}
    finally:
        conn.close()