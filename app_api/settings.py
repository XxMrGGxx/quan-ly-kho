from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from database import get_db
from app_api.auth import get_current_user, check_permission

router = APIRouter()

class SettingsPayload(BaseModel):
    allow_negative_stock: int = 0
    ncc_debt_limit: float = 0
    kh_debt_limit: float = 0



@router.get("/inventory/settings")
async def get_settings(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    # admin can access settings; các role khác sẽ bị check_permission chặn
    if user.get('role') != 'admin' and not check_permission(user, 'settings', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền truy cập cài đặt")


    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM settings WHERE id=1")
        row = c.fetchone()
        if not row:
            return {
                "settings": {
                    "allow_negative_stock": 0,
                    "ncc_debt_limit": 0,
                    "kh_debt_limit": 0,
                }
            }
        return {"settings": dict(row)}

    finally:
        conn.close()

@router.put("/inventory/settings")
async def put_settings(payload: SettingsPayload, request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    if user.get('role') != 'admin' and not check_permission(user, 'settings', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền chỉnh sửa cài đặt")


    conn = get_db()
    c = conn.cursor()
    try:
        allow_val = 1 if int(payload.allow_negative_stock) == 1 else 0
        ncc_val = float(payload.ncc_debt_limit or 0)
        kh_val = float(payload.kh_debt_limit or 0)

        c.execute("""
            INSERT INTO settings (id, allow_negative_stock, ncc_debt_limit, kh_debt_limit)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET allow_negative_stock=excluded.allow_negative_stock,
                                          ncc_debt_limit=excluded.ncc_debt_limit,
                                          kh_debt_limit=excluded.kh_debt_limit,
                                          updated_at=datetime('now','localtime')
        """, (allow_val, ncc_val, kh_val))
        conn.commit()
        return {
            "message": "Đã lưu cài đặt ứng dụng",
            "settings": {
                "allow_negative_stock": allow_val,
                "ncc_debt_limit": ncc_val,
                "kh_debt_limit": kh_val
            }
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

