"""
Hệ thống quản lý bản quyền - License Manager
Bảo mật bằng hardware fingerprint + mã hóa AES-256 + HMAC-SHA256

Trạng thái bản quyền:
  - none:      Chưa có bản quyền, chưa dùng thử
  - trial:     Đang dùng thử (30 ngày)
  - trial_expired: Hết hạn dùng thử
  - active:    Đã kích hoạt bản quyền
  - expired:   Bản quyền đã hết hạn
"""
import hashlib
import hmac
import json
import os
import platform
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import re
from path_utils import get_app_dir
from database import get_db

# --- Hằng số ---
LICENSE_FILE = None  # Khởi tạo sau qua _get_license_file()
SECRET_SALT = b"AnTinSolution_WMS_2024_SecretKey_DoNotShare"
MASTER_KEY = "ANTIN-WMS-MASTER-2024"
TRIAL_DAYS = 15

# Cache hardware fingerprint 1 lần cho toàn bộ vòng đời app
# Tránh fingerprint thay đổi do uuid.getnode()/network/hostname
_FINGERPRINT_CACHE = None
_MACHINE_ID_CACHE = None

# --- Trạng thái bản quyền ---
STATUS_NONE = "none"
STATUS_TRIAL = "trial"
STATUS_TRIAL_EXPIRED = "trial_expired"
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"


def _get_license_file() -> Path:
    """Resolve license file path relative to app directory (PyInstaller-safe)."""
    global LICENSE_FILE
    if LICENSE_FILE is None:
        LICENSE_FILE = get_app_dir() / "data" / "license.dat"
    return LICENSE_FILE


# ===== DATABASE TRACKER (chống reset trial bằng cách xóa file) =====

def _track_license_in_db(fingerprint: str, mode: str, expiry_date: str = None, license_key: str = None):
    """Ghi nhận trạng thái license vào DB để chống reset"""
    try:
        conn = get_db()
        c = conn.cursor()
        now_str = datetime.now().isoformat()
        
        existing = c.execute(
            "SELECT id, mode FROM license_tracker WHERE fingerprint=?",
            (fingerprint,)
        ).fetchone()
        
        if existing:
            update_fields = ["last_verified=?"]
            params = [now_str]
            
            if mode == "trial":
                # Chỉ update nếu chưa có full license
                c.execute("SELECT mode FROM license_tracker WHERE fingerprint=?", (fingerprint,))
                current_mode = c.fetchone()[0]
                if current_mode == "full" and mode == "trial":
                    conn.close()
                    return  # Không ghi đè full license bằng trial
            elif mode == "full":
                update_fields.append("mode='full'")
                if expiry_date:
                    update_fields.append(f"trial_end_date='{expiry_date}'")
                if license_key:
                    update_fields.append(f"full_license_key='{license_key}'")
            
            update_fields_str = ", ".join(update_fields)
            c.execute(f"UPDATE license_tracker SET {update_fields_str} WHERE fingerprint=?", params + [fingerprint])
        else:
            now_iso = datetime.now().isoformat()
            trial_end = expiry_date or (datetime.now() + timedelta(days=TRIAL_DAYS)).isoformat()
            c.execute(
                """INSERT INTO license_tracker 
                   (fingerprint, mode, trial_start_date, trial_end_date, full_license_key, last_verified)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fingerprint, mode, now_iso, trial_end, license_key or "", now_iso)
            )
        
        conn.commit()
        conn.close()
    except Exception as e:
        pass  # DB tracking là secondary, không block luồng chính


def _check_trial_in_db(fingerprint: str) -> dict:
    """Kiểm tra trạng thái trial từ DB (dùng khi file license.dat bị xóa)"""
    try:
        conn = get_db()
        c = conn.cursor()
        row = c.execute(
            "SELECT mode, trial_start_date, trial_end_date, full_license_key FROM license_tracker WHERE fingerprint=?",
            (fingerprint,)
        ).fetchone()
        conn.close()
        
        if row:
            return {
                "found": True,
                "mode": row[0],
                "trial_start_date": row[1],
                "trial_end_date": row[2],
                "full_license_key": row[3]
            }
        return {"found": False}
    except Exception:
        return {"found": False}


def get_hardware_fingerprint() -> str:
    """Lấy hardware fingerprint của máy tính (không thể giả mạo)
    
    Kết quả được cache 1 lần cho toàn bộ vòng đời app để tránh
    fingerprint thay đổi do uuid.getnode()/network/hostname.
    """
    global _FINGERPRINT_CACHE
    if _FINGERPRINT_CACHE is not None:
        return _FINGERPRINT_CACHE
    
    components = []
    
    system = platform.system()
    
    try:
        if system == "Windows":
            # Flag để tránh bật cửa sổ console khi chạy subprocess ở chế độ noconsole
            CREATE_NO_WINDOW = 0x08000000
            
            # CPU ID
            result = subprocess.run(['wmic', 'cpu', 'get', 'ProcessorId'], 
                                  capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            components.append(result.stdout.strip())
            
            # Motherboard serial
            result = subprocess.run(['wmic', 'baseboard', 'get', 'serialnumber'],
                                  capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            components.append(result.stdout.strip())
            
            # BIOS serial
            result = subprocess.run(['wmic', 'bios', 'get', 'serialnumber'],
                                  capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            components.append(result.stdout.strip())
            
            # Disk serial
            result = subprocess.run(['wmic', 'diskdrive', 'get', 'serialnumber'],
                                  capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            components.append(result.stdout.strip())
            
        elif system == "Linux":
            # Machine ID
            try:
                with open('/etc/machine-id', 'r') as f:
                    components.append(f.read().strip())
            except:
                pass
            
            # Product UUID
            try:
                result = subprocess.run(['cat', '/sys/class/dmi/id/product_uuid'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    components.append(result.stdout.strip())
            except:
                pass
            
            # CPU info
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'Serial' in line or 'Hardware' in line:
                            components.append(line.strip())
            except:
                pass
                
            # Board serial
            try:
                result = subprocess.run(['cat', '/sys/class/dmi/id/board_serial'],
                                      capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip() not in ['', 'None', 'N/A']:
                    components.append(result.stdout.strip())
            except:
                pass
                
        elif system == "Darwin":  # macOS
            result = subprocess.run(['system_profiler', 'SPHardwareDataType'],
                                  capture_output=True, text=True)
            components.append(result.stdout)
    except:
        pass
    
    # Fallback: MAC address (luôn có)
    mac = ':'.join(re.findall('..', '%012x' % uuid.getnode()))
    components.append(mac)
    
    # Platform info
    components.append(platform.node())
    components.append(platform.machine())
    
    # Tạo fingerprint từ tất cả components
    combined = '|'.join(filter(None, components))
    fingerprint = hashlib.sha256((combined + MASTER_KEY).encode()).hexdigest()
    
    # Cache fingerprint cho toàn bộ vòng đời app
    _FINGERPRINT_CACHE = fingerprint
    return fingerprint


def derive_key(fingerprint: str) -> bytes:
    """Tạo encryption key từ hardware fingerprint"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SECRET_SALT,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(fingerprint.encode()))
    return key


def generate_license_key(fingerprint: str, company_name: str, 
                          expiry_days: int = 365, 
                          max_users: int = 10) -> str:
    """
    Tạo license key cho một máy cụ thể (chỉ admin mới có thể tạo)
    Format: XXXX-XXXX-XXXX-XXXX-XXXX
    """
    payload = {
        "fp": fingerprint[:16],  # Partial fingerprint
        "co": company_name,
        "ex": (datetime.now() + timedelta(days=expiry_days)).isoformat(),
        "mu": max_users,
        "ts": int(time.time()),
        "v": "1.0"
    }
    
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    # Sign với MASTER_KEY
    signature = hmac.new(
        (MASTER_KEY + fingerprint).encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()[:16]
    
    # Encode payload
    encoded = base64.b64encode(payload_str.encode()).decode()
    
    # Tạo key format đẹp
    combined = (encoded + signature).replace('=', '').replace('+', 'A').replace('/', 'B')
    
    # Chia thành blocks 5 ký tự
    blocks = []
    chunk_size = max(4, len(combined) // 5)
    for i in range(0, len(combined), chunk_size):
        blocks.append(combined[i:i+chunk_size].upper())
    
    return '-'.join(blocks[:8])  # Max 8 blocks


def generate_offline_key(fingerprint: str, company: str, 
                          expiry_days: int = 365, 
                          max_users: int = 50) -> str:
    """
    Tạo offline activation key dạng OFFLINE- [base64_json]-[signature]
    Key này được verify_and_activate() xử lý ở định dạng OFFLINE-...
    """
    # Tạo payload JSON với đầy đủ thông tin
    payload = {
        "fp_p": fingerprint[:16],  # Partial fingerprint để verify
        "co": company,
        "ex_d": expiry_days,
        "mu": max_users,
        "ts": int(time.time()),
    }
    
    payload_str = json.dumps(payload, separators=(',', ':'))
    
    # Encode payload thành base64 URL-safe
    encoded_payload = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip('=')
    
    # Tạo chữ ký từ payload + master key + fingerprint (32 hex chars = 128 bits)
    raw_data = payload_str + MASTER_KEY + fingerprint[:16]
    signature = hashlib.sha256(raw_data.encode()).hexdigest()[:32].upper()
    
    # Format: OFFLINE-{encoded_payload}-{signature}
    return f"OFFLINE-{encoded_payload}-{signature}"


def save_license(license_data: dict):
    """Lưu license file được mã hóa"""
    fingerprint = get_hardware_fingerprint()
    key = derive_key(fingerprint)
    f = Fernet(key)
    
    encrypted = f.encrypt(json.dumps(license_data).encode())
    
    lic_path = _get_license_file()
    os.makedirs(str(lic_path.parent), exist_ok=True)
    with open(lic_path, 'wb') as file:
        # Thêm checksum
        checksum = hashlib.sha256(encrypted + fingerprint.encode()).hexdigest()
        file.write(checksum.encode() + b'\n' + encrypted)
    
    # Ghi vào DB tracker để chống reset
    mode = license_data.get("mode", "trial")
    expiry = license_data.get("expiry")
    key_val = license_data.get("key")
    _track_license_in_db(fingerprint, mode, expiry, key_val)


def init_trial() -> dict:
    """
    Khởi tạo bản dùng thử 30 ngày (tự động gọi khi lần đầu chạy phần mềm
    và chưa có license file nào).
    
    Kiểm tra DB tracker trước khi init để chống reset trial bằng cách xóa file.
    """
    fingerprint = get_hardware_fingerprint()
    
    # Kiểm tra DB tracker trước
    db_record = _check_trial_in_db(fingerprint)
    if db_record["found"]:
        db_mode = db_record["mode"]
        
        if db_mode == "full":
            # Full license existed before, don't allow trial
            return {
                "valid": False,
                "company": "",
                "expiry": datetime.now().isoformat(),
                "max_users": 0,
                "activated_at": datetime.now().isoformat(),
                "fingerprint": fingerprint,
                "key": "",
                "mode": "none"
            }
        
        # Trial mode - restore from DB instead of creating new one
        db_end = db_record.get("trial_end_date")
        if db_end:
            try:
                trial_end = datetime.fromisoformat(db_end)
                if trial_end > datetime.now():
                    # Trial still valid, restore file
                    trial_data = {
                        "valid": True,
                        "company": "Dùng thử",
                        "expiry": trial_end.isoformat(),
                        "max_users": 3,
                        "activated_at": db_record.get("trial_start_date", datetime.now().isoformat()),
                        "fingerprint": fingerprint,
                        "key": "TRIAL",
                        "mode": "trial"
                    }
                    save_license(trial_data)
                    return trial_data
            except:
                pass
    
    # Thực sự chưa có trial nào => tạo mới
    now = datetime.now()
    trial_until = now + timedelta(days=TRIAL_DAYS)
    
    trial_data = {
        "valid": True,
        "company": "Dùng thử",
        "expiry": trial_until.isoformat(),
        "max_users": 3,
        "activated_at": now.isoformat(),
        "fingerprint": fingerprint,
        "key": "TRIAL",
        "mode": "trial"
    }
    save_license(trial_data)
    return trial_data


def verify_and_activate(activation_key: str) -> dict:
    """
    Xác thực và kích hoạt license (chỉ áp dụng cho full license).
    Returns: {"valid": bool, "message": str, "info": dict}
    """
    fingerprint = get_hardware_fingerprint()
    
    # Normalize key: strip whitespace, remove spaces
    # KHÔNG dùng .upper() vì sẽ làm hỏng base64 payload của OFFLINE key!
    clean_key = activation_key.strip().replace(' ', '')
    
    # Demo mode: accept specific test key (case-insensitive check)
    if clean_key.upper() == "DEMO-ANTN-2024-FREE":
        license_data = {
            "valid": True,
            "company": "DEMO - An Tín Solution",
            "expiry": (datetime.now() + timedelta(days=30)).isoformat(),
            "max_users": 3,
            "activated_at": datetime.now().isoformat(),
            "fingerprint": fingerprint,
            "key": clean_key.upper(),
            "mode": "trial"
        }
        save_license(license_data)
        return {"valid": True, "message": "Kích hoạt thành công (Dùng thử 30 ngày)", "info": license_data}
    
    # --- OFFLINE KEY FORMAT (OFFLINE-{base64_payload}-{signature}) ---
    # Check prefix case-insensitively, but preserve case of payload for base64
    if clean_key.upper().startswith("OFFLINE-"):
        # Split on '-' but preserve the original case of each part
        raw_parts = clean_key.split('-', 2)  # Max 3 parts: OFFLINE, payload, signature
        
        # Handle case where payload has embedded '-' by checking prefix
        if len(raw_parts) >= 2 and raw_parts[0].upper() == "OFFLINE":
            # The rest after "OFFLINE-" is <payload>-<signature>
            rest = clean_key[len("OFFLINE-"):]  # Preserve original case
            
            # FIX: Signature is always 32 hex characters (SHA256 hex digest[:32])
            # Extract from end to avoid confusion with '-' characters in URL-safe base64 payload
            if len(rest) < 33:  # Need at least payload + '-' + 32-char signature
                return {"valid": False, "message": "Key offline không đúng định dạng", "info": {}}
            
            signature_block = rest[-32:]  # Last 32 chars = signature (uppercase hex)
            encoded_payload = rest[:-33]  # Everything before the '-' separator + signature
        else:
            return {"valid": False, "message": "Key offline không đúng định dạng", "info": {}}
        
        try:
            # Add padding back for base64.urlsafe_b64decode
            missing_padding = len(encoded_payload) % 4
            if missing_padding:
                encoded_payload += '=' * (4 - missing_padding)

            decoded_payload_bytes = base64.urlsafe_b64decode(encoded_payload.encode())
            payload_data = json.loads(decoded_payload_bytes.decode())
        except (ValueError, json.JSONDecodeError):
            return {"valid": False, "message": "Key offline bị lỗi định dạng payload", "info": {}}
        
        # Verify partial fingerprint
        if payload_data.get("fp_p") != fingerprint[:16]:
            return {"valid": False, "message": "Key offline không khớp với máy tính này (fingerprint)", "info": {}}
        
        # Re-calculate signature to verify (32 hex chars = 128 bits)
        raw_payload_str = json.dumps(payload_data, separators=(',', ':'))
        raw_data = raw_payload_str + MASTER_KEY + fingerprint[:16]
        recalculated_signature = hashlib.sha256(raw_data.encode()).hexdigest()[:32].upper()
        
        if recalculated_signature != signature_block.upper():
            return {"valid": False, "message": "Key offline không hợp lệ (chữ ký)", "info": {}}
        
        # Extract info from payload
        company_name = payload_data.get("co", "An Tín Solution")
        expiry_days = payload_data.get("ex_d", 365)
        max_users = payload_data.get("mu", 50)
        
        license_data = {
            "valid": True,
            "company": company_name,
            "expiry": (datetime.now() + timedelta(days=expiry_days)).isoformat(),
            "max_users": max_users,
            "activated_at": datetime.now().isoformat(),
            "fingerprint": fingerprint,
            "key": clean_key.upper(),
            "mode": "full"
        }
        save_license(license_data)
        return {"valid": True, "message": f"Kích hoạt thành công - Full version {expiry_days} ngày", "info": license_data}

    return {"valid": False, "message": "Key không hợp lệ hoặc không đúng định dạng", "info": {}}


def check_license() -> dict:
    """
    Kiểm tra trạng thái bản quyền hiện tại.
    Returns: {
        "valid": bool,
        "status": "none" | "trial" | "trial_expired" | "active" | "expired",
        "message": str,
        "info": dict
    }
    """
    lic_path = _get_license_file()
    fingerprint = get_hardware_fingerprint()
    
    # Trường hợp chưa có license file => kiểm tra DB tracker
    if not lic_path.exists():
        db_record = _check_trial_in_db(fingerprint)
        if db_record["found"]:
            db_mode = db_record["mode"]
            db_end = db_record["trial_end_date"]
            
            if db_mode == "full":
                # Đã có full license trong DB nhưng file bị mất => yêu cầu kích hoạt lại
                return {
                    "valid": False,
                    "status": STATUS_NONE,
                    "message": "File license bị mất. Vui lòng nhập lại mã kích hoạt để khôi phục.",
                    "info": {}
                }
            
            # Trial mode - check expiry from DB
            try:
                trial_end = datetime.fromisoformat(db_end) if db_end else datetime.now()
            except:
                trial_end = datetime.now()
            
            days_left = (trial_end - datetime.now()).days
            
            if datetime.now() > trial_end:
                return {
                    "valid": False,
                    "status": STATUS_TRIAL_EXPIRED,
                    "message": f"Phiên bản dùng thử đã hết hạn. Vui lòng kích hoạt bản quyền để tiếp tục sử dụng.",
                    "info": {
                        "days_left": days_left,
                        "expiry": db_end,
                        "mode": "trial",
                        "max_users": 3,
                        "company": "Dùng thử"
                    }
                }
            
            # Trial còn hạn - khôi phục file license
            try:
                now = datetime.now()
                trial_data = {
                    "valid": True,
                    "company": "Dùng thử",
                    "expiry": trial_end.isoformat(),
                    "max_users": 3,
                    "activated_at": db_record.get("trial_start_date", now.isoformat()),
                    "fingerprint": fingerprint,
                    "key": "TRIAL",
                    "mode": "trial"
                }
                save_license(trial_data)
            except:
                pass
            
            return {
                "valid": True,
                "status": STATUS_TRIAL,
                "message": f"Đang dùng thử - còn {days_left} ngày",
                "info": {
                    "days_left": days_left,
                    "expiry": db_end,
                    "mode": "trial",
                    "max_users": 3,
                    "company": "Dùng thử"
                }
            }
        
        # Không có record trong DB => none
        return {
            "valid": False,
            "status": STATUS_NONE,
            "message": "Chưa kích hoạt phần mềm",
            "info": {}
        }
    
    try:
        with open(lic_path, 'rb') as file:
            content = file.read()
        
        # Split checksum và data
        newline_pos = content.index(b'\n')
        stored_checksum = content[:newline_pos].decode()
        encrypted = content[newline_pos+1:]
        
        # Verify checksum (chống copy file sang máy khác)
        expected_checksum = hashlib.sha256(encrypted + fingerprint.encode()).hexdigest()
        if stored_checksum != expected_checksum:
            return {
                "valid": False,
                "status": STATUS_NONE,
                "message": "File license không hợp lệ hoặc đã bị copy từ máy khác",
                "info": {}
            }
        
        # Decrypt
        key = derive_key(fingerprint)
        f = Fernet(key)
        decrypted = f.decrypt(encrypted)
        license_data = json.loads(decrypted)
        
        # Verify fingerprint match
        if license_data.get("fingerprint") != fingerprint:
            return {
                "valid": False,
                "status": STATUS_NONE,
                "message": "License không khớp với máy tính này",
                "info": {}
            }
        
        # Lấy mode (trial | full)
        mode = license_data.get("mode", "full")
        expiry_str = license_data.get("expiry", "")
        
        # Check expiry
        try:
            expiry = datetime.fromisoformat(expiry_str)
        except:
            expiry = datetime.now() + timedelta(days=365)
        
        days_left = (expiry - datetime.now()).days
        license_data["days_left"] = days_left
        
        if datetime.now() > expiry:
            days_expired = abs(days_left)
            if mode == "trial":
                return {
                    "valid": False,
                    "status": STATUS_TRIAL_EXPIRED,
                    "message": f"Phiên bản dùng thử đã hết hạn {days_expired} ngày trước. Vui lòng kích hoạt bản quyền để tiếp tục sử dụng.",
                    "info": license_data
                }
            else:
                return {
                    "valid": False,
                    "status": STATUS_EXPIRED,
                    "message": f"Bản quyền đã hết hạn {days_expired} ngày trước",
                    "info": license_data
                }
        
        # License còn hạn
        if mode == "trial":
            return {
                "valid": True,
                "status": STATUS_TRIAL,
                "message": f"Đang dùng thử - còn {days_left} ngày",
                "info": license_data
            }
        else:
            return {
                "valid": True,
                "status": STATUS_ACTIVE,
                "message": f"Bản quyền hợp lệ - còn {days_left} ngày",
                "info": license_data
            }
        
    except Exception as e:
        return {
            "valid": False,
            "status": STATUS_NONE,
            "message": f"Lỗi đọc license: {str(e)}",
            "info": {}
        }


def get_license_restrictions() -> dict:
    """
    Trả về các giới hạn của phần mềm dựa trên trạng thái bản quyền.
    Được gọi bởi middleware để enforce.
    """
    license_status = check_license()
    status = license_status.get("status", STATUS_NONE)
    info = license_status.get("info", {})
    max_users = info.get("max_users", 0)
    
    # Mặc định: Không cho phép truy cập gì cả
    restrictions = {
        "can_access": False,           # Có thể truy cập phần mềm?
        "can_manage_users": False,     # Có thể quản lý users?
        "can_export": False,           # Có thể xuất excel/pdf?
        "max_users": 0,                # Số user tối đa
        "show_warning": False,         # Hiển thị cảnh báo?
        "warning_message": "",         # Nội dung cảnh báo
        "redirect_to_license": False,  # Chuyển hướng đến trang license?
    }
    
    if status == STATUS_NONE:
        restrictions.update({
            "can_access": False,
            "redirect_to_license": True,
            "warning_message": "Phần mềm chưa được kích hoạt. Vui lòng kích hoạt để sử dụng."
        })
    
    elif status == STATUS_TRIAL:
        restrictions.update({
            "can_access": True,
            "can_manage_users": True,
            "can_export": True,
            "max_users": max_users or 3,
            "show_warning": True,
            "warning_message": f"Bạn đang dùng thử (còn {info.get('days_left', 0)} ngày). Một số tính năng bị giới hạn."
        })
    
    elif status == STATUS_TRIAL_EXPIRED:
        restrictions.update({
            "can_access": False,
            "redirect_to_license": True,
            "warning_message": "Phiên bản dùng thử đã hết hạn. Vui lòng kích hoạt bản quyền để tiếp tục."
        })
    
    elif status == STATUS_ACTIVE:
        restrictions.update({
            "can_access": True,
            "can_manage_users": True,
            "can_export": True,
            "max_users": max_users or 50,
            "show_warning": False,
        })
    
    elif status == STATUS_EXPIRED:
        restrictions.update({
            "can_access": False,
            "redirect_to_license": True,
            "warning_message": "Bản quyền đã hết hạn. Vui lòng gia hạn để tiếp tục sử dụng."
        })
    
    return restrictions


def get_machine_id() -> str:
    """Lấy Machine ID để người dùng gửi cho admin xin key"""
    fp = get_hardware_fingerprint()
    # Chỉ trả về phần đủ để identify, không lộ toàn bộ
    return f"ANTIN-{fp[:8].upper()}-{fp[8:16].upper()}"


def decode_license_key(activation_key: str) -> dict:
    """
    Giải mã key bản quyền để hiển thị thông tin TRƯỚC KHI kích hoạt.
    KHÔNG thay đổi trạng thái license, chỉ đọc và hiển thị.

    Returns: {
        "valid": bool,
        "message": str,
        "info": {
            "company": str,
            "expiry_days": int,
            "max_users": int,
            "created_at": str,
            "fingerprint_partial": str
        }
    }
    """
    # Get current machine fingerprint for comparison
    fingerprint = get_hardware_fingerprint()

    # Normalize key
    clean_key = activation_key.strip().replace(' ', '')

    # Demo mode key
    if clean_key.upper() == "DEMO-ANTN-2024-FREE":
        return {
            "valid": True,
            "message": "Demo key - 30 ngày",
            "info": {
                "company": "DEMO - An Tín Solution",
                "expiry_days": 30,
                "max_users": 3,
                "created_at": datetime.now().isoformat(),
                "fingerprint_partial": ""
            }
        }

    # OFFLINE KEY FORMAT
    if clean_key.upper().startswith("OFFLINE-"):
        rest = clean_key[len("OFFLINE-"):]

        if len(rest) < 33:
            return {"valid": False, "message": "Key offline không đúng định dạng", "info": {}}

        signature_block = rest[-32:]
        encoded_payload = rest[:-33]

        try:
            # Add padding back for base64.urlsafe_b64decode
            missing_padding = len(encoded_payload) % 4
            if missing_padding:
                encoded_payload += '=' * (4 - missing_padding)

            decoded_payload_bytes = base64.urlsafe_b64decode(encoded_payload.encode())
            payload_data = json.loads(decoded_payload_bytes.decode())
        except (ValueError, json.JSONDecodeError):
            return {"valid": False, "message": "Key offline bị lỗi định dạng payload", "info": {}}

        # Verify partial fingerprint match
        fp_match = payload_data.get("fp_p") == fingerprint[:16]
        fp_partial = payload_data.get("fp_p", "")

        # Try to verify signature (optional - might fail if fingerprint doesn't match)
        try:
            raw_payload_str = json.dumps(payload_data, separators=(',', ':'))
            raw_data = raw_payload_str + MASTER_KEY + fingerprint[:16]
            recalculated_sig = hashlib.sha256(raw_data.encode()).hexdigest()[:32].upper()
            sig_valid = (recalculated_sig == signature_block.upper())
        except:
            sig_valid = False

        # Extract info from payload
        company_name = payload_data.get("co", "Unknown")
        expiry_days = payload_data.get("ex_d", 0)
        max_users = payload_data.get("mu", 0)
        timestamp = payload_data.get("ts", 0)

        # Calculate created date from timestamp
        try:
            created_at = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except:
            created_at = "Unknown"

        # Build response
        if not fp_match:
            return {
                "valid": False,
                "message": f"Key không khớp với máy này (期望: {fingerprint[:16]}, 实际: {fp_partial})",
                "info": {
                    "company": company_name,
                    "expiry_days": expiry_days,
                    "max_users": max_users,
                    "created_at": created_at,
                    "fingerprint_partial": fp_partial,
                    "fingerprint_match": False
                }
            }

        if not sig_valid:
            return {
                "valid": False,
                "message": "Key không hợp lệ (chữ ký không đúng)",
                "info": {
                    "company": company_name,
                    "expiry_days": expiry_days,
                    "max_users": max_users,
                    "created_at": created_at,
                    "fingerprint_partial": fp_partial,
                    "fingerprint_match": True
                }
            }

        # All valid
        return {
            "valid": True,
            "message": "Key hợp lệ - sẵn sàng để kích hoạt",
            "info": {
                "company": company_name,
                "expiry_days": expiry_days,
                "max_users": max_users,
                "created_at": created_at,
                "fingerprint_partial": fp_partial,
                "fingerprint_match": True
            }
        }

    # Unknown format
    return {"valid": False, "message": "Key không đúng định dạng", "info": {}}