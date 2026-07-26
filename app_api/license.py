
from fastapi import APIRouter, HTTPException, Request
from database import get_db
from app_api.auth import get_current_user
from license_manager import (
    check_license, verify_and_activate, get_machine_id,
    init_trial, get_license_restrictions, _get_license_file,
    get_hardware_fingerprint, decode_license_key
)

router = APIRouter()


def require_admin(request: Request):
    """Kiểm tra người dùng hiện tại có phải admin không"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Chỉ admin mới có quyền truy cập")
    return user


def _ensure_profile_row(conn):
    c = conn.cursor()
    c.execute("SELECT * FROM company_profile WHERE id=1")
    row = c.fetchone()
    if not row:
        c.execute("""
            INSERT INTO company_profile (id, company_name, short_name, tax_code, phone, email, address, representative, website, bank_account, bank_name)
            VALUES (1, 'An Tín Solution', 'An Tín WMS', '', '', 'antin.solution@gmail.com', 'TP. Đồng Nai', '', '', '2060112348888', 'MB-Bank')
        """)
        conn.commit()
        c.execute("SELECT * FROM company_profile WHERE id=1")
        row = c.fetchone()
    return dict(row)

@router.get("/check")
async def get_license_status(request: Request):
    require_admin(request)
    return check_license()

@router.get("/machine-id")
async def get_machine_id_endpoint(request: Request):
    require_admin(request)
    return {"machine_id": get_machine_id()}

@router.post("/activate")
async def activate_license(request: Request, body: dict = {}):
    require_admin(request)
    key = body.get("key", "")
    return verify_and_activate(key)

@router.post("/deactivate")
async def deactivate_license(request: Request):
    require_admin(request)
    """Hủy kích hoạt - xóa file license và DB tracker"""
    try:
        lic_path = _get_license_file()
        if lic_path.exists():
            lic_path.unlink()
        
        # Xóa DB tracker cho fingerprint này
        try:
            fingerprint = get_hardware_fingerprint()
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM license_tracker WHERE fingerprint=?", (fingerprint,))
            conn.commit()
            conn.close()
        except:
            pass
        
        return {"success": True, "message": "Đã hủy kích hoạt thành công"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi: {str(e)}"}

@router.post("/init-trial")
async def start_trial(request: Request):
    require_admin(request)
    """Khởi tạo bản dùng thử 30 ngày"""
    # Chỉ cho phép khởi tạo trial nếu chưa có license
    current = check_license()
    if current.get("status") in ("trial", "active"):
        return {"success": False, "message": "Đã có bản quyền, không thể khởi tạo dùng thử"}
    
    trial_data = init_trial()
    return {"success": True, "message": "Đã khởi tạo bản dùng thử 30 ngày", "info": trial_data}

@router.get("/restrictions")
async def get_restrictions(request: Request):
    require_admin(request)
    """Trả về các giới hạn dựa trên trạng thái bản quyền"""
    return get_license_restrictions()


@router.post("/decode-key")
async def decode_key(request: Request, body: dict = {}):
    require_admin(request)
    """
    Giải mã key bản quyền để hiển thị thông tin TRƯỚC KHI kích hoạt.
    """
    key = body.get("key", "")
    if not key:
        return {"valid": False, "message": "Vui lòng nhập mã kích hoạt", "info": {}}

    return decode_license_key(key)


@router.get("/company-profile")
async def get_company_profile(request: Request):
    require_admin(request)
    conn = get_db()
    try:
        profile = _ensure_profile_row(conn)
        return {"profile": profile}
    finally:
        conn.close()


@router.put("/company-profile")
async def update_company_profile(request: Request, data: dict):
    require_admin(request)
    conn = get_db()
    try:
        profile = _ensure_profile_row(conn)
        updates = {
            "company_name": data.get("company_name", profile["company_name"]),
            "short_name": data.get("short_name", profile["short_name"]),
            "tax_code": data.get("tax_code", profile["tax_code"]),
            "phone": data.get("phone", profile["phone"]),
            "email": data.get("email", profile["email"]),
            "address": data.get("address", profile["address"]),
            "representative": data.get("representative", profile["representative"]),
            "website": data.get("website", profile["website"]),
            "bank_account": data.get("bank_account", profile["bank_account"]),
            "bank_name": data.get("bank_name", profile["bank_name"]),
        }
        c = conn.cursor()
        c.execute("""
            UPDATE company_profile
            SET company_name=?, short_name=?, tax_code=?, phone=?, email=?, address=?,
                representative=?, website=?, bank_account=?, bank_name=?, updated_at=datetime('now','localtime')
            WHERE id=1
        """, (
            updates["company_name"], updates["short_name"], updates["tax_code"], updates["phone"],
            updates["email"], updates["address"], updates["representative"], updates["website"],
            updates["bank_account"], updates["bank_name"]
        ))
        conn.commit()
        return {"success": True, "profile": updates, "message": "Đã cập nhật thông tin đơn vị"}
    finally:
        conn.close()
