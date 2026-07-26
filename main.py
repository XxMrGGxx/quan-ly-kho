"""
An Tín Solution - WMS Backend Entry Point (Working with Python 3.14)
"""
import uvicorn
import socket
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse


from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import time
from contextlib import asynccontextmanager
import threading
import webbrowser
import os
import sys
import secrets
from wms_overlay import start_overlay_thread

# Chống crash khi build exe với noconsole (redirect stdout/stderr/stdin)
if getattr(sys, 'frozen', False):
    devnull = open(os.devnull, 'w')
    sys.stdout = devnull
    sys.stderr = devnull
    sys.stdin = open(os.devnull, 'r')

# Import các module API
from app_api import auth, license, products, partners, inventory, warehouses, reports, debt, settings as settings_api, data_management 


from path_utils import get_app_dir, get_resources_dir
from database import init_database

# ===== LIFESPAN: init database + auto-trial on startup =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_database()
    except Exception:
        pass
    # Auto initialize trial if no license exists
    try:
        from license_manager import check_license, init_trial
        lic = check_license()
        if lic.get("status") == "none":
            init_trial()
    except Exception:
        pass
    yield


# ===== APP INIT =====
app = FastAPI(title="WMS AnTin Solution", version="1.0.0", lifespan=lifespan)

APP_DIR = get_app_dir()        # thư mục cạnh exe - lưu data/
RES_DIR = get_resources_dir()  # thư mục chứa static/, templates/


# ===== CORS MIDDLEWARE =====
# Whitelist origins - chỉ cho phép các origin đáng tin cậy
CORS_ORIGINS = [
    f"http://localhost:8081",
    f"http://127.0.0.1:8081",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)


# ===== CSRF PROTECTION =====
# Lưu trữ CSRF tokens: mapping {token: created_at_timestamp}
# Token có hạn 1 giờ
_csrf_tokens: dict = {}

CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

def _generate_csrf_token() -> str:
    """Tạo CSRF token mới"""
    token = secrets.token_urlsafe(32)
    _csrf_tokens[token] = time.time()
    return token

def _cleanup_expired_csrf_tokens():
    """Xóa CSRF token hết hạn (> 1 giờ)"""
    now = time.time()
    expired = [t for t, ts in _csrf_tokens.items() if now - ts > 3600]
    for t in expired:
        _csrf_tokens.pop(t, None)

def _validate_csrf_token(token: str) -> bool:
    """Kiểm tra CSRF token có hợp lệ không"""
    if not token:
        return False
    _cleanup_expired_csrf_tokens()
    if token in _csrf_tokens:
        # Single-use token: xóa sau khi dùng
        del _csrf_tokens[token]
        return True
    return False

# CSRF cookie name (non-httponly để JS đọc được)
CSRF_COOKIE_NAME = "wms_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    """Middleware chống CSRF:
    - GET/HEAD/OPTIONS/TRACE: không cần kiểm tra, chỉ set cookie nếu chưa có
    - POST/PUT/DELETE: kiểm tra X-CSRF-Token header trùng với cookie
    """
    path = request.url.path
    method = request.method
    
    # Bỏ qua kiểm tra cho static files và auth
    skip_paths = ["/static", "/favicon.ico", "/api/auth/login", "/api/auth/logout"]
    should_skip = any(path.startswith(sp) for sp in skip_paths)
    
    # Nếu là safe method (GET, HEAD, OPTIONS): set CSRF cookie nếu chưa có
    if method in CSRF_SAFE_METHODS:
        # Chuẩn bị CSRF token TRƯỚC khi call_next, để render() dùng chung token này
        existing_csrf = request.cookies.get(CSRF_COOKIE_NAME)
        if existing_csrf and existing_csrf in _csrf_tokens:
            request.state._csrf_token = existing_csrf
        else:
            request.state._csrf_token = _generate_csrf_token()
        
        response = await call_next(request)
        
        # Set cookie nếu request chưa có cookie hợp lệ
        if not should_skip:
            if not existing_csrf or existing_csrf not in _csrf_tokens:
                response.set_cookie(
                    key=CSRF_COOKIE_NAME,
                    value=request.state._csrf_token,
                    httponly=False,
                    max_age=3600,
                    samesite="lax",
                    path="/"
                )
        return response
    
    # Mutating method (POST, PUT, DELETE): kiểm tra CSRF
        # Lấy token từ header
        header_token = request.headers.get(CSRF_HEADER_NAME, "")
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")
        
        # Kiểm tra: header token phải khớp với cookie token
        if not header_token or not cookie_token:
            return JSONResponse(
                status_code=403,
                content={"detail": "Thiếu CSRF token. Vui lòng tải lại trang và thử lại."}
            )
        
        if header_token != cookie_token:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token không hợp lệ. Vui lòng tải lại trang và thử lại."}
            )
        
        if not _validate_csrf_token(header_token):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token đã hết hạn. Vui lòng tải lại trang và thử lại."}
            )
        
        # Token hợp lệ, cho phép request đi tiếp
        response = await call_next(request)
        
        # Sau khi CSRF token bị tiêu thụ (single-use), cấp token mới
        # Set cả cookie mới + response header để JS đọc và cập nhật window.WMS.csrfToken
        new_csrf_token = _generate_csrf_token()
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=new_csrf_token,
            httponly=False,
            max_age=3600,
            samesite="lax",
            path="/"
        )
        response.headers[CSRF_HEADER_NAME] = new_csrf_token
        return response
    
    response = await call_next(request)
    return response


# ===== SECURITY HEADERS MIDDLEWARE =====
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Thêm security headers cho mọi response (P4.1, P4.3)"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # CSP: chỉ cho phép script từ chính domain, inline scripts hợp lệ
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' unpkg.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' unpkg.com https://unpkg.com; "
        "img-src 'self' data: https://*.tile.openstreetmap.org; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    )
    return response


# ===== AUTH MIDDLEWARE =====
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Các route công khai không cần kiểm tra
    public_paths = [
        "/auth", 
        "/api/auth/login", 
        "/api/auth/verify", 
        "/static", 
        "/favicon.ico",
        "/docs",
        "/openapi.json",
        "/redoc"
    ]
    
    path = request.url.path
    
    # Cho phép truy cập không cần auth
    allowed_without_auth = public_paths
    for allowed_path in allowed_without_auth:
        if path.startswith(allowed_path):
            return await call_next(request)
    
    # Kiểm tra token từ cookie
    token = request.cookies.get("wms_token")
    
    # Nếu không có token trong cookie, thử từ header
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    # Verify token
    is_valid = False
    user_role = None
    if token:
        from app_api.auth import active_tokens
        token_data = active_tokens.get(token)
        if token_data and token_data.get("expires", 0) > int(time.time()):
            is_valid = True
            user_role = token_data.get("role")
            if not user_role:
                from app_api.auth import get_current_user_from_token
                user = get_current_user_from_token(token)
                if user:
                    user_role = user.get("role")
                    token_data["role"] = user_role
    
    if is_valid:
        # Chỉ admin mới được truy cập trang license và API license
        license_paths = [
            "/license",
            "/api/license/check",
            "/api/license/machine-id",
            "/api/license/activate",
            "/api/license/init-trial",
            "/api/license/restrictions",
            "/api/license/deactivate",
            "/api/license/decode-key",
        ]
        for lic_path in license_paths:
            if path.startswith(lic_path):
                if user_role != 'admin':
                    if path.startswith("/api/"):
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Chỉ admin mới có quyền truy cập mục bản quyền"}
                        )
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Chỉ admin mới có quyền truy cập", "redirect": "/index"}
                    )
                return await call_next(request)
        
        # Kiểm tra license status
        from license_manager import check_license
        lic = check_license()
        status = lic.get("status", "none")

        # Nếu chưa có license (none) => CHẶN - không tự động tạo trial
        # Người dùng phải tự kích hoạt bằng tay
        if status == "none":
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Phần mềm chưa được kích hoạt. Vui lòng kích hoạt để sử dụng.", "redirect": "/license"}
                )
            return RedirectResponse(url="/license")
        
        # Nếu hết hạn trial hoặc hết hạn license => chặn
        if status in ("trial_expired", "expired"):
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": lic.get("message", "Bản quyền đã hết hạn"), "redirect": "/license"}
                )
            return RedirectResponse(url="/license")
        
        # Saler restriction
        if user_role == "saler":
            # saler can access: sales-entry, customers (create new customer), sales-map
            allowed_pages = ["/sales-entry", "/customers", "/auth", "/sales-map"]
            if not path.startswith("/api/") and path not in allowed_pages:
                return RedirectResponse(url="/sales-entry")
        
        # Token hợp lệ + license hợp lệ, cho phép truy cập
        return await call_next(request)
    
    # Nếu là API request, trả về JSON 401
    if path.startswith("/api/"):
        return JSONResponse(
            status_code=401, 
            content={"detail": "Unauthorized", "redirect": "/auth"}
        )
    
    # Redirect về trang login cho các route frontend
    return RedirectResponse(url="/auth")


# ===== STATIC FILES =====
static_dir = str(RES_DIR / "static")
Path(static_dir).mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ===== JINJA2 SETUP =====
templates_dir = RES_DIR / "templates"
templates_dir.mkdir(exist_ok=True)

jinja_env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=select_autoescape(['html', 'xml']),
)

def _get_or_create_csrf_token(request: Request) -> str:
    """Lấy CSRF token từ cookie hoặc từ request.state (do middleware chuẩn bị)"""
    # Ưu tiên dùng token từ middleware (đảm bảo đồng bộ cookie và embedded)
    if hasattr(request.state, '_csrf_token'):
        return request.state._csrf_token
    # Fallback: đọc từ cookie
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    if existing and existing in _csrf_tokens:
        return existing
    token = _generate_csrf_token()
    return token


def render(template_name: str, context: dict = None, request: Request = None):
    """Helper function để render template và trả về HTMLResponse.
    Nếu có request, sẽ embed CSRF token vào template cho JS sử dụng."""
    if context is None:
        context = {}
    
    csrf_token = None
    if request:
        csrf_token = _get_or_create_csrf_token(request)
        context["csrf_token"] = csrf_token
    
    try:
        template = jinja_env.get_template(template_name)
        content = template.render(**context)
        
        # Nếu có CSRF token, thêm dòng script embedded vào trước </body>
        if csrf_token:
            embed_script = f'<script>window.WMS=window.WMS||{{}};window.WMS.csrfToken="{csrf_token}";</script>\n'
            content = content.replace("</body>", embed_script + "</body>")
        
        return HTMLResponse(content=content)
    except Exception as e:
        error_html = f"<h1>Template Error</h1><p>Template: {template_name}</p><p>Error: {str(e)}</p>"
        return HTMLResponse(content=error_html, status_code=500)


# ===== API ROUTERS =====
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(license.router, prefix="/api/license", tags=["License"])
app.include_router(products.router, prefix="/api/products", tags=["Products"])
app.include_router(partners.router, prefix="/api", tags=["Partners"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(settings_api.router, prefix="/api", tags=["Settings"])

app.include_router(inventory.router_import_export, prefix="/api", tags=["Orders"])


app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(reports.router_dashboard, prefix="/api", tags=["Dashboard"])

app.include_router(warehouses.router, prefix="/api/warehouses", tags=["Warehouses"])
app.include_router(debt.router, prefix="/api", tags=["Debt"])

# ===== DATA MANAGEMENT ROUTER =====
app.include_router(data_management.router, prefix="/api", tags=["Data Management"])

# ===== SALES MAP ROUTER =====
from app_api import sales_map
app.include_router(sales_map.router, prefix="/api", tags=["Sales Map"])


# ===== FRONTEND ROUTES =====

@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/auth")

@app.get("/auth")
async def auth_page(request: Request):
    return render("auth.html", {"request": request})

@app.get("/index")
async def index_page(request: Request):
    return render("index.html", {"request": request, "active_page": "dashboard"})

@app.get("/products")
async def products_page(request: Request):
    return render("products.html", {"request": request, "active_page": "products"})

@app.get("/customers")
async def customers_page(request: Request):
    return render("customers.html", {"request": request, "active_page": "customers"})

@app.get("/suppliers")
async def suppliers_page(request: Request):
    return render("suppliers.html", {"request": request, "active_page": "suppliers"})

@app.get("/import")
async def import_page(request: Request):
    return render("import.html", {"request": request, "active_page": "import"})

@app.get("/import/new")
async def import_new_page(request: Request):
    return render("import_form.html", {"request": request, "active_page": "import", "mode": "create"})

@app.get("/import/{order_id}/edit")
async def import_edit_page(request: Request, order_id: int):
    return render("import_form.html", {"request": request, "active_page": "import", "mode": "edit", "order_id": order_id})

@app.get("/export")
async def export_page(request: Request):
    return render("export.html", {"request": request, "active_page": "export"})

@app.get("/export/new")
async def export_new_page(request: Request):
    return render("export_form.html", {"request": request, "active_page": "export", "mode": "create"})

@app.get("/export/{order_id}/edit")
async def export_edit_page(request: Request, order_id: int):
    return render("export_form.html", {"request": request, "active_page": "export", "mode": "edit", "order_id": order_id})

@app.get("/reports")
async def reports_page(request: Request):
    return render("reports.html", {"request": request, "active_page": "reports"})

@app.get("/users")
async def users_page(request: Request):
    return render("users.html", {"request": request, "active_page": "users"})

@app.get("/inventory")
async def inventory_page(request: Request):
    return render("inventory.html", {"request": request, "active_page": "inventory"})

@app.get("/sales-entry")
async def sales_entry_page(request: Request):
    return render("sales_entry.html", {"request": request, "active_page": "sales_entry"})

@app.get("/warehouses")
async def warehouses_page(request: Request):
    return render("warehouses.html", {"request": request, "active_page": "warehouses"})

@app.get("/license")
async def license_page(request: Request):
    """Trang quản lý bản quyền - chỉ dành cho admin"""
    from app_api.auth import get_current_user
    current_user = get_current_user(request)
    if not current_user or current_user.get('role') != 'admin':
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return render("license.html", {"request": request, "active_page": "license"})

@app.get("/settings")
async def settings_page(request: Request):
    """Trang cài đặt - chỉ dành cho admin (chưa triển khai chức năng)"""
    from app_api.auth import get_current_user
    current_user = get_current_user(request)
    if not current_user or current_user.get('role') != 'admin':
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return render("settings.html", {"request": request, "active_page": "settings"})

@app.get("/debt")
async def debt_page(request: Request):
    """Trang quản lý công nợ"""
    return render("debt.html", {"request": request, "active_page": "debt"})


@app.get("/debt/payment")
async def debt_payment_page(request: Request):
    """Trang thanh toán công nợ ẩn - chỉ gọi từ debt.html"""
    from fastapi.responses import HTMLResponse
    from pathlib import Path
    
    template_path = Path(__file__).parent / "templates" / "debt_payment.html"
    if not template_path.exists():
        return HTMLResponse(content="<h1>Trang thanh toán chưa được cấu hình</h1>", status_code=404)
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Lỗi: {str(e)}</h1>", status_code=500)

@app.get("/sales-map")
async def sales_map_page(request: Request):
    """Trang bản đồ theo dõi nhân viên sale"""
    return render("sales_map.html", {"request": request, "active_page": "sales_map"})



# ===== API: LẤY IP WAN / WAN URL =====
from app_api.wan_utils import build_wan_url
from app_api.qr_utils import make_qr_data_uri


@app.get("/api/system/wan-url")
async def get_wan_url_api():

    """Return WAN url like http(s)://{public_ip}:{port}.

    Frontend uses it to generate QR for salesmen.
    """
    try:
        port = 8081
        # Auto-detect: use https if certificate files exist
        cert_file = Path(__file__).parent / "cert.pem"
        key_file = Path(__file__).parent / "key.pem"
        use_ssl = cert_file.exists() and key_file.exists()
        protocol = "https" if use_ssl else "http"
        url = build_wan_url(port=port, path="", protocol=protocol)
        if not url:
            return JSONResponse(status_code=200, content={"wan_url": None, "qr_data_uri": None, "detail": "Không lấy được IP WAN"})

        # Generate QR PNG as data URI
        qr_data_uri = make_qr_data_uri(url, box_size=5, border=2)
        return {"wan_url": url, "qr_data_uri": qr_data_uri}

    except Exception:
        return JSONResponse(status_code=200, content={"wan_url": None, "detail": "Lỗi khi lấy IP WAN"})


# ===== API: LẤY IP MÁY =====
@app.get("/api/system/ip")
async def get_server_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return {"ip": ip}
    except Exception:
        return {"ip": "127.0.0.1"}


# ===== MAIN ENTRY POINT (Tự động mở trình duyệt) =====
if __name__ == "__main__":

    port = 8081
    use_ssl = False  # Đặt False nếu muốn chạy HTTP thuần

    # Đường dẫn certificate
    cert_file = Path(__file__).parent / "cert.pem"
    key_file = Path(__file__).parent / "key.pem"

    if use_ssl and cert_file.exists() and key_file.exists():
        protocol = "https"
        ssl_kwargs = {
            "ssl_certfile": str(cert_file),
            "ssl_keyfile": str(key_file),
        }
    else:
        protocol = "http"
        ssl_kwargs = {}

    url = f"{protocol}://localhost:{port}"

    # Hàm chạy server trong luồng riêng
    def run_server():
        # reload=False là bắt buộc khi chạy thread để tránh lỗi
        # Pass app object directly instead of string reference for PyInstaller compatibility
        uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_config=None, access_log=False, **ssl_kwargs)

    # Khởi động WMS overlay (góc trên bên trái)
    start_overlay_thread()

    # Khởi động server
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(2)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        # Vòng lặp vô hạn để giữ main thread sống
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        os._exit(0)
