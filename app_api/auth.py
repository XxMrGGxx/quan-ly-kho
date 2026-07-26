from fastapi import APIRouter, HTTPException, Header, Request, Response
from pydantic import BaseModel
import secrets
import time
import json
from datetime import datetime
from typing import Optional, Dict, List
from database import get_db, hash_password, verify_password


router = APIRouter()

# Lưu trữ token tạm thời
active_tokens: Dict[str, dict] = {}

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "staff"
    department: Optional[str] = None
    notes: Optional[str] = None
    warehouse_ids: List[int] = []

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[int] = None
    notes: Optional[str] = None
    warehouse_ids: Optional[List[int]] = None

def generate_token(username: str, user_id: int, role: str = None) -> str:
    """Tạo token mới"""
    timestamp = int(time.time())
    random_part = secrets.token_hex(16)
    token = f"{user_id}.{timestamp}.{random_part}"
    
    active_tokens[token] = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "expires": timestamp + 86400  # 24 hours
    }
    
    # Dọn dẹp token cũ
    cleanup_expired_tokens()
    
    return token

def cleanup_expired_tokens():
    """Xóa các token đã hết hạn"""
    current_time = int(time.time())
    expired = [token for token, data in active_tokens.items() 
               if data.get("expires", 0) < current_time]
    for token in expired:
        del active_tokens[token]

# Rate limiting: dictionary lưu số lần đăng nhập thất bại
_login_attempts: Dict[str, dict] = {}

def check_login_rate_limit(username: str):
    """Kiểm tra rate limit cho đăng nhập - tối đa 5 lần sai trong 15 phút"""
    import time
    now = int(time.time())
    key = f"login:{username}"
    
    # Cleanup old entries
    if key in _login_attempts:
        if now - _login_attempts[key].get("first_attempt", now) > 900:  # 15 phút
            del _login_attempts[key]
            return True
    
    attempts = _login_attempts.get(key, {"count": 0, "first_attempt": now})
    if attempts["count"] >= 5:
        raise HTTPException(status_code=429, detail="Quá nhiều lần đăng nhập sai. Vui lòng thử lại sau 15 phút.")
    return True

def record_failed_login(username: str):
    """Ghi nhận lần đăng nhập thất bại"""
    import time
    now = int(time.time())
    key = f"login:{username}"
    if key not in _login_attempts:
        _login_attempts[key] = {"count": 0, "first_attempt": now}
    _login_attempts[key]["count"] += 1

def record_successful_login(username: str):
    """Reset đếm khi đăng nhập thành công"""
    key = f"login:{username}"
    if key in _login_attempts:
        del _login_attempts[key]

def get_current_user_from_token(token: str):
    """Lấy user từ token"""
    if not token:
        return None
    
    # Xử lý token có thể có prefix "Bearer "
    if token.startswith("Bearer "):
        token = token[7:]
    
    # Kiểm tra token
    token_data = active_tokens.get(token)
    if not token_data:
        return None
    
    # Kiểm tra hết hạn
    if token_data.get("expires", 0) < int(time.time()):
        del active_tokens[token]
        return None
    
    # Lấy thông tin user từ database
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=? AND is_active=1", (token_data["user_id"],))
    user = c.fetchone()
    conn.close()
    
    if not user:
        return None
    
    return dict(user)

def get_current_user(
    request: Request,
    authorization: Optional[str] = None
):
    """Lấy thông tin user hiện tại từ token (cookie hoặc header)"""
    token = None

    # Thử lấy token từ cookie trước
    if request is not None:
        token = request.cookies.get("wms_token")

    # Nếu không có, thử lấy từ header
    if not token:
        if isinstance(authorization, str) and authorization:
            token = authorization
        elif request is not None:
            token = request.headers.get("Authorization") or request.headers.get("authorization")

    return get_current_user_from_token(token)

def check_permission(user, module: str, action: str) -> bool:
    """Kiểm tra quyền của user"""
    if not user:
        return False
    if user['role'] == 'admin':
        return True
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT can_view, can_create, can_edit, can_delete, can_export 
        FROM permissions 
        WHERE role=? AND module=?
    """, (user['role'], module))
    perm = dict(c.fetchone() or {})
    conn.close()
    
    if not perm:
        return False
    
    action_map = {
        'view': perm['can_view'],
        'create': perm['can_create'],
        'edit': perm['can_edit'],
        'delete': perm['can_delete'],
        'export': perm['can_export']
    }
    
    return action_map.get(action, 0) == 1


def get_user_assigned_warehouses(user_id: int):
    """Lấy danh sách warehouse_id được gán cho user"""
    if not user_id:
        return []
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT warehouse_id FROM user_warehouses WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [row['warehouse_id'] for row in rows]


def get_warehouse_filter_clause(user, warehouse_alias: str = 'warehouse_id'):
    """Tạo điều kiện SQL để lọc theo kho của user (trả về tuple: clause, params)"""
    if not user or user.get('role') == 'admin':
        return "", []
    
    wh_ids = get_user_assigned_warehouses(user.get('id'))
    if not wh_ids:
        return f" AND {warehouse_alias} IN (SELECT 1 WHERE 1=0)", []
    
    placeholders = ','.join(['?'] * len(wh_ids))
    return f" AND {warehouse_alias} IN ({placeholders})", wh_ids


def check_warehouse_access(user, warehouse_id: int) -> bool:
    """Kiểm tra user có quyền truy cập warehouse_id không"""
    if not user or user.get('role') == 'admin':
        return True
    
    wh_ids = get_user_assigned_warehouses(user.get('id'))
    return warehouse_id in wh_ids if wh_ids else False

# ========== AUDIT LOGGING ==========

def _log_audit(user_id: int, action: str, module: str = None, record_id: int = None, 
               old_data: dict = None, new_data: dict = None, ip_address: str = None):
    """Ghi audit log vào database"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO audit_log (user_id, action, module, record_id, old_data, new_data, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, action, module, record_id,
              json.dumps(old_data) if old_data else None,
              json.dumps(new_data) if new_data else None,
              ip_address,
              datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Không throw lỗi nếu audit log thất bại


# ========== AUTHENTICATION ==========

@router.post("/login")
async def login(credentials: LoginRequest, response: Response):
    """Đăng nhập"""
    # Kiểm tra rate limit
    check_login_rate_limit(credentials.username)
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM users WHERE username=? AND is_active=1", (credentials.username,))
    user = c.fetchone()
    
    if not user or not verify_password(credentials.password, user["password"]):
        record_failed_login(credentials.username)
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
    
    # Reset rate limit khi đăng nhập thành công
    record_successful_login(credentials.username)
    
    # Cập nhật last_login
    c.execute("UPDATE users SET last_login=? WHERE id=?", 
              (datetime.now().isoformat(), user["id"]))
    conn.commit()
    conn.close()
    
    # Tạo token mới
    token = generate_token(user["username"], user["id"], user["role"])
    
    user_data = dict(user)
    user_data.pop("password", None)
    
    # Tự động phát hiện HTTPS từ request
    import os as _os
    is_https = _os.path.exists(_os.path.join(_os.path.dirname(__file__), '..', 'cert.pem'))

    # Set cookie an toàn
    response.set_cookie(
        key="wms_token",
        value=token,
        httponly=True,  # Bảo mật: Không cho JavaScript đọc cookie để chống XSS
        max_age=86400,
        samesite="lax",
        secure=is_https,  # Tự động: True nếu có cert (HTTPS), False nếu HTTP
        path="/"
    )
    
    # Audit log: đăng nhập thành công
    _log_audit(
        user_id=user["id"],
        action="login",
        module="auth",
        new_data={"username": user["username"]},
    )
    
    return {
        "token": token,
        "user": user_data,
        "message": "Đăng nhập thành công"
    }

@router.post("/logout")
async def logout(request: Request, response: Response):
    """Đăng xuất"""
    token = request.cookies.get("wms_token")
    user_id = None
    username = None
    if token and token in active_tokens:
        user_id = active_tokens[token].get("user_id")
        username = active_tokens[token].get("username")
        del active_tokens[token]
    
    response.delete_cookie("wms_token")
    
    # Audit log: đăng xuất
    if user_id:
        _log_audit(
            user_id=user_id,
            action="logout",
            module="auth",
            new_data={"username": username},
        )
    
    return {"message": "Đã đăng xuất"}

@router.get("/verify")
async def verify_token(request: Request):
    """Kiểm tra token có còn hiệu lực không"""
    user = get_current_user(request)
    if user:
        user_data = dict(user)
        user_data.pop("password", None)
        return {"valid": True, "user": user_data}
    return {"valid": False}

@router.get("/me")
async def get_current_user_info(request: Request):
    """Lấy thông tin user hiện tại"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user_data = dict(user)
    user_data.pop("password", None)
    
    # Lấy danh sách kho được gán
    wh_ids = get_user_assigned_warehouses(user['id'])
    user_data['warehouse_ids'] = wh_ids
    
    # Lấy thông tin chi tiết các kho - sử dụng parameterized query an toàn
    if wh_ids:
        conn = get_db()
        c = conn.cursor()
        # Tạo placeholders an toàn: chỉ gồm dấu ?
        placeholders = ','.join(['?'] * len(wh_ids))
        c.execute(
            f"SELECT id, code, name FROM warehouses WHERE id IN ({placeholders}) AND is_active=1",
            wh_ids
        )
        user_data['warehouses'] = [dict(row) for row in c.fetchall()]
        conn.close()
    else:
        user_data['warehouses'] = []
    
    return user_data

# ========== QUẢN LÝ NGƯỜI DÙNG ==========

@router.get("/users")
async def get_users(request: Request):
    """Lấy danh sách người dùng"""
    current_user = get_current_user(request)
    if not current_user or not check_permission(current_user, 'users', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền truy cập")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, username, full_name, email, phone, role, department, 
               is_active, last_login, created_at, notes 
        FROM users 
        ORDER BY id
    """)
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    
    # Bổ sung warehouse_ids cho từng user
    for u in users:
        u['warehouse_ids'] = get_user_assigned_warehouses(u['id'])
    
    return {"items": users}

@router.post("/users")
async def create_user(user: UserCreate, request: Request):
    """Tạo người dùng mới"""
    current_user = get_current_user(request)
    if not current_user or not check_permission(current_user, 'users', 'create'):
        raise HTTPException(status_code=403, detail="Không có quyền tạo người dùng")
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute("""
            INSERT INTO users (username, password, full_name, email, phone, role, department, notes, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user.username, hash_password(user.password), user.full_name, 
              user.email, user.phone, user.role, user.department, user.notes, current_user['id']))
        conn.commit()
        
        new_user_id = c.lastrowid
        
        if user.warehouse_ids:
            for wh_id in user.warehouse_ids:
                c.execute("INSERT OR IGNORE INTO user_warehouses (user_id, warehouse_id) VALUES (?, ?)",
                          (new_user_id, wh_id))
            conn.commit()
        
        return {"id": new_user_id, "message": "Tạo người dùng thành công"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=f"Lỗi: {str(e)}")
    finally:
        conn.close()

@router.put("/users/{user_id}")
async def update_user(user_id: int, user: UserUpdate, request: Request):
    """Cập nhật thông tin người dùng"""
    current_user = get_current_user(request)
    if not current_user or not check_permission(current_user, 'users', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền cập nhật")
    
    conn = get_db()
    c = conn.cursor()
    
    updates = []
    params = []
    
    if user.full_name is not None:
        updates.append("full_name=?")
        params.append(user.full_name)
    if user.email is not None:
        updates.append("email=?")
        params.append(user.email)
    if user.phone is not None:
        updates.append("phone=?")
        params.append(user.phone)
    if user.role is not None:
        updates.append("role=?")
        params.append(user.role)
    if user.department is not None:
        updates.append("department=?")
        params.append(user.department)
    if user.is_active is not None:
        updates.append("is_active=?")
        params.append(user.is_active)
    if user.notes is not None:
        updates.append("notes=?")
        params.append(user.notes)
    
    if updates:
        params.append(user_id)
        c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
    
    if user.warehouse_ids is not None:
        c.execute("DELETE FROM user_warehouses WHERE user_id = ?", (user_id,))
        for wh_id in user.warehouse_ids:
            c.execute("INSERT OR IGNORE INTO user_warehouses (user_id, warehouse_id) VALUES (?, ?)",
                      (user_id, wh_id))
        conn.commit()
    
    conn.close()
    return {"message": "Cập nhật thành công"}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request):
    """Xóa người dùng (vô hiệu hóa)"""
    current_user = get_current_user(request)
    if not current_user or not check_permission(current_user, 'users', 'delete'):
        raise HTTPException(status_code=403, detail="Không có quyền xóa")
    
    if user_id == current_user['id']:
        raise HTTPException(status_code=400, detail="Không thể xóa chính mình")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
    
    # Xóa token của user bị vô hiệu hóa
    tokens_to_remove = [t for t, data in active_tokens.items() if data.get("user_id") == user_id]
    for token in tokens_to_remove:
        del active_tokens[token]
    
    conn.commit()
    conn.close()
    return {"message": "Đã vô hiệu hóa người dùng"}

@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, password_data: dict, request: Request):
    """Đặt lại mật khẩu"""
    current_user = get_current_user(request)
    if not current_user or not check_permission(current_user, 'users', 'edit'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    new_password = password_data.get("new_password")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 6 ký tự")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_password), user_id))
    conn.commit()
    conn.close()
    
    # P3.3: Xóa tất cả token của user đó để buộc đăng nhập lại
    tokens_to_remove = [t for t, data in active_tokens.items() if data.get("user_id") == user_id]
    for token in tokens_to_remove:
        del active_tokens[token]
    
    # Ghi audit log
    _log_audit(
        user_id=current_user['id'],
        action="reset_password",
        module="users",
        record_id=user_id,
        new_data={"password_reset": True},
    )
    
    return {"message": "Đặt lại mật khẩu thành công. Người dùng sẽ cần đăng nhập lại."}

# ========== PHÂN QUYỀN ==========

@router.get("/permissions/{role}")
async def get_role_permissions(role: str, request: Request):
    """Lấy quyền của một role"""
    current_user = get_current_user(request)
    if not current_user or not check_permission(current_user, 'users', 'view'):
        raise HTTPException(status_code=403, detail="Không có quyền")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT module, can_view, can_create, can_edit, can_delete, can_export 
        FROM permissions 
        WHERE role=?
    """, (role,))
    permissions = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"role": role, "permissions": permissions}

@router.put("/permissions/{role}")
async def update_role_permissions(role: str, perm_data: dict, request: Request):
    """Cập nhật quyền cho một role"""
    current_user = get_current_user(request)
    if not current_user or current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Chỉ admin mới có quyền phân quyền")
    
    conn = get_db()
    c = conn.cursor()
    
    permissions = perm_data.get("permissions", {})
    for module, perms in permissions.items():
        c.execute("""
            UPDATE permissions 
            SET can_view=?, can_create=?, can_edit=?, can_delete=?, can_export=?
            WHERE role=? AND module=?
        """, (perms.get('can_view', 0), perms.get('can_create', 0),
              perms.get('can_edit', 0), perms.get('can_delete', 0),
              perms.get('can_export', 0), role, module))
    
    conn.commit()
    conn.close()
    return {"message": "Cập nhật quyền thành công"}

@router.get("/modules")
async def get_modules():
    """Lấy danh sách các module"""
    modules = [
        {"id": "products", "name": "Hàng hóa"},
        {"id": "customers", "name": "Khách hàng"},
        {"id": "suppliers", "name": "Nhà cung cấp"},
        {"id": "inventory", "name": "Tồn kho"},
        {"id": "import_orders", "name": "Nhập kho"},
        {"id": "export_orders", "name": "Xuất kho"},
        {"id": "warehouses", "name": "Quản lý Kho"},
        {"id": "reports", "name": "Báo cáo"},
        {"id": "users", "name": "Người dùng"},
        {"id": "settings", "name": "Cài đặt"}
    ]
    return {"modules": modules}