"""
Sales Map - GPS Tracking API for Salesmen
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from database import get_db
from app_api.auth import get_current_user

router = APIRouter()


class GPSLogCreate(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = 0
    address: Optional[str] = None
    note: Optional[str] = None


class GPSLogResponse(BaseModel):
    id: int
    user_id: int
    username: str
    full_name: str
    latitude: float
    longitude: float
    accuracy: float
    address: Optional[str]
    note: Optional[str]
    created_at: str


@router.post("/sales/gps-log")
async def log_gps(data: GPSLogCreate, request: Request):
    """Ghi nhận vị trí GPS của nhân viên sale"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO sales_gps_log (user_id, latitude, longitude, accuracy, address, note)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user['id'], data.latitude, data.longitude, data.accuracy, data.address, data.note))
    conn.commit()
    log_id = c.lastrowid
    conn.close()
    
    return {"id": log_id, "detail": "GPS location logged successfully"}


@router.get("/sales/gps-log", response_model=List[GPSLogResponse])
async def get_gps_logs(
    request: Request,
    days: Optional[int] = 30,
    user_id: Optional[int] = None,
    limit: Optional[int] = 500
):
    """Lấy lịch sử GPS của nhân viên sale (mặc định 30 ngày gần nhất)"""
    current_user = get_current_user(request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_db()
    c = conn.cursor()

    since_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    # Nếu là admin/manager: xem tất cả hoặc theo user_id, chỉ lấy saler đang active
    # Nếu là saler: chỉ xem của chính mình
    params = [since_date]
    user_filter = ""

    if current_user['role'] in ('admin', 'manager'):
        user_filter = "AND u.role = 'saler' AND u.is_active = 1"
        if user_id:
            user_filter += " AND g.user_id = ?"
            params.append(user_id)
    else:
        # Saler chỉ thấy data của mình
        user_filter = "AND g.user_id = ?"
        params.append(current_user['id'])

    params.append(limit)

    c.execute(f"""
        SELECT g.id, g.user_id, u.username, u.full_name,
               g.latitude, g.longitude, g.accuracy,
               g.address, g.note, g.created_at
        FROM sales_gps_log g
        JOIN users u ON u.id = g.user_id
        WHERE g.created_at >= ?
        {user_filter}
        ORDER BY g.created_at DESC
        LIMIT ?
    """, params)
    
    rows = c.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        result.append({
            "id": row['id'],
            "user_id": row['user_id'],
            "username": row['username'],
            "full_name": row['full_name'],
            "latitude": row['latitude'],
            "longitude": row['longitude'],
            "accuracy": row['accuracy'],
            "address": row['address'],
            "note": row['note'],
            "created_at": row['created_at']
        })
    
    return result


@router.get("/sales/gps-log/latest", response_model=Optional[GPSLogResponse])
async def get_latest_gps(request: Request):
    """Lấy vị trí GPS mới nhất của user hiện tại"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT g.id, g.user_id, u.username, u.full_name,
               g.latitude, g.longitude, g.accuracy,
               g.address, g.note, g.created_at
        FROM sales_gps_log g
        JOIN users u ON u.id = g.user_id
        WHERE g.user_id = ?
        ORDER BY g.created_at DESC
        LIMIT 1
    """, (user['id'],))
    
    row = c.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "id": row['id'],
        "user_id": row['user_id'],
        "username": row['username'],
        "full_name": row['full_name'],
        "latitude": row['latitude'],
        "longitude": row['longitude'],
        "accuracy": row['accuracy'],
        "address": row['address'],
        "note": row['note'],
        "created_at": row['created_at']
    }


@router.get("/sales/gps-log/users")
async def get_active_users(request: Request):
    """Lấy danh sách user có dữ liệu GPS (dành cho admin/manager filter)"""
    current_user = get_current_user(request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = get_db()
    c = conn.cursor()
    
    if current_user['role'] in ('admin', 'manager'):
        c.execute("""
            SELECT DISTINCT u.id, u.username, u.full_name
            FROM sales_gps_log g
            JOIN users u ON u.id = g.user_id
            WHERE u.is_active = 1 AND u.role = 'saler'
            ORDER BY u.full_name
        """)
    else:
        c.execute("""
            SELECT u.id, u.username, u.full_name
            FROM users u
            WHERE u.id = ? AND u.is_active = 1
        """, (current_user['id'],))
    
    rows = c.fetchall()
    conn.close()
    
    return [{"id": row['id'], "username": row['username'], "full_name": row['full_name']} for row in rows]


@router.get("/sales/gps-log/latest-all", response_model=List[GPSLogResponse])
async def get_all_latest_gps(
    request: Request,
    user_id: Optional[int] = None
):
    """Lấy vị trí GPS mới nhất của nhân viên sale (dành cho admin/manager).
    Có thể filter theo user_id để lấy vị trí mới nhất của 1 nhân viên cụ thể.
    """
    current_user = get_current_user(request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    conn = get_db()
    c = conn.cursor()
    
    if current_user['role'] in ('admin', 'manager'):
        if user_id:
            # Lấy vị trí mới nhất của 1 user cụ thể
            c.execute("""
                SELECT g.id, g.user_id, u.username, u.full_name,
                       g.latitude, g.longitude, g.accuracy,
                       g.address, g.note, g.created_at
                FROM sales_gps_log g
                JOIN users u ON u.id = g.user_id
                WHERE g.user_id = ? AND u.is_active = 1 AND u.role = 'saler'
                ORDER BY g.created_at DESC
                LIMIT 1
            """, (user_id,))
        else:
            c.execute("""
                SELECT g.id, g.user_id, u.username, u.full_name,
                       g.latitude, g.longitude, g.accuracy,
                       g.address, g.note, g.created_at
                FROM sales_gps_log g
                INNER JOIN (
                    SELECT user_id, MAX(created_at) AS max_time
                    FROM sales_gps_log
                    GROUP BY user_id
                ) latest ON g.user_id = latest.user_id AND g.created_at = latest.max_time
                JOIN users u ON u.id = g.user_id
                WHERE u.is_active = 1 AND u.role = 'saler'
                ORDER BY u.full_name
            """)
    else:
        # Saler chỉ thấy vị trí của chính mình
        c.execute("""
            SELECT g.id, g.user_id, u.username, u.full_name,
                   g.latitude, g.longitude, g.accuracy,
                   g.address, g.note, g.created_at
            FROM sales_gps_log g
            JOIN users u ON u.id = g.user_id
            WHERE g.user_id = ?
            ORDER BY g.created_at DESC
            LIMIT 1
        """, (current_user['id'],))
    
    rows = c.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        result.append({
            "id": row['id'],
            "user_id": row['user_id'],
            "username": row['username'],
            "full_name": row['full_name'],
            "latitude": row['latitude'],
            "longitude": row['longitude'],
            "accuracy": row['accuracy'],
            "address": row['address'],
            "note": row['note'],
            "created_at": row['created_at']
        })
    
    return result
