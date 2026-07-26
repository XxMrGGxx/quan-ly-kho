"""
Database SQLite - Warehouse Management System
"""
import sqlite3
import hashlib
import os
from path_utils import get_app_dir

DB_PATH = None

def _get_db_path():
    """Ensure DB path is resolved relative to app directory"""
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = str(get_app_dir() / "data" / "warehouse.db")
    return DB_PATH

def get_db():
    """Get database connection"""
    app_dir = get_app_dir()
    os.makedirs(str(app_dir / "data"), exist_ok=True)
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # PRAGMA settings - tối ưu hiệu năng
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")      # Giảm fsync, write nhanh hơn ~2-3x
    conn.execute("PRAGMA cache_size=-32768")       # Cache 32MB (âm = KB)
    conn.execute("PRAGMA temp_store=MEMORY")       # Bảng tạm/CTE trong RAM
    conn.execute("PRAGMA mmap_size=268435456")     # mmap 256MB cho sequential scan
    # page_size=4096: CHỈ set được TRƯỚC khi tạo DB, không thể đổi sau
    
    return conn


def get_company_profile():
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM company_profile WHERE id=1")
        row = c.fetchone()
        return dict(row) if row else {
            "company_name": "An Tín Solution",
            "short_name": "An Tín WMS",
            "tax_code": "",
            "phone": "",
            "email": "info@antinsolution.com",
            "address": "TP. Ho Chi Minh",
            "representative": "",
            "website": "",
            "bank_account": "",
            "bank_name": ""
        }
    finally:
        conn.close()

# Password hashing constants
PBKDF2_ITERATIONS = 600000
PBKDF2_SALT_LENGTH = 16

def hash_password(password: str) -> str:
    """
    Hash password with PBKDF2-HMAC-SHA256 + random salt.
    Format: $pbkdf2-sha256$iterations${salt_hex}${hash_hex}
    Nâng cấp từ SHA256 cũ lên PBKDF2 để chống brute-force.
    """
    import secrets as _secrets
    salt = _secrets.token_hex(PBKDF2_SALT_LENGTH)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        PBKDF2_ITERATIONS
    ).hex()
    return f"$pbkdf2-sha256${PBKDF2_ITERATIONS}${salt}${pwd_hash}"


def _hash_password_legacy(password: str) -> str:
    """Legacy SHA256 hashing (giữ lại để verify mật khẩu cũ)"""
    return hashlib.sha256((password + "AnTinWMS_Salt2024").encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify password against stored hash.
    Tự động detect legacy SHA256 vs PBKDF2 format.
    """
    if stored_hash.startswith("$pbkdf2-sha256$"):
        # New PBKDF2 format: $pbkdf2-sha256$iterations$salt$hash
        parts = stored_hash.split('$')
        if len(parts) != 5:
            return False
        _, algo, iterations_str, salt, stored_pwd_hash = parts
        try:
            iterations = int(iterations_str)
        except ValueError:
            return False
        computed_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            iterations
        ).hex()
        return computed_hash == stored_pwd_hash
    else:
        # Legacy SHA256 format
        return stored_hash == _hash_password_legacy(password)

def init_database():
    """Khởi tạo database với tất cả các bảng"""
    conn = get_db()
    c = conn.cursor()
    
    # ========== USERS & AUTH ==========
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        role TEXT NOT NULL DEFAULT 'staff',  -- admin, manager, staff, viewer
        department TEXT,
        is_active INTEGER DEFAULT 1,
        last_login TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        created_by INTEGER,
        notes TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        module TEXT NOT NULL,  -- products, customers, suppliers, inventory, reports, users, settings
        can_view INTEGER DEFAULT 0,
        can_create INTEGER DEFAULT 0,
        can_edit INTEGER DEFAULT 0,
        can_delete INTEGER DEFAULT 0,
        can_export INTEGER DEFAULT 0,
        UNIQUE(role, module)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        module TEXT,
        record_id INTEGER,
        old_data TEXT,
        new_data TEXT,
        ip_address TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS company_profile (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        company_name TEXT DEFAULT 'An Tín Solution',
        short_name TEXT DEFAULT 'An Tín WMS',
        tax_code TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        address TEXT DEFAULT '',
        representative TEXT DEFAULT '',
        website TEXT DEFAULT '',
        bank_account TEXT DEFAULT '',
        bank_name TEXT DEFAULT '',
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )''')

    # ========== SETTINGS (Config hệ thống) ==========
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        allow_negative_stock INTEGER NOT NULL DEFAULT 0, -- 0: không cho phép, 1: cho phép
        ncc_debt_limit REAL DEFAULT 0,   -- hạn mức công nợ nhà cung cấp
        kh_debt_limit REAL DEFAULT 0,    -- hạn mức công nợ khách hàng
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    )''')


    
    # ========== LICENSE TRACKER (chống reset trial bằng cách xóa file) ==========
    c.execute('''CREATE TABLE IF NOT EXISTS license_tracker (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'trial',  -- trial, full
        trial_start_date TEXT,
        trial_end_date TEXT,
        full_license_key TEXT,
        last_verified TEXT DEFAULT (datetime('now','localtime')),
        created_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(fingerprint)
    )''')
    
    # ========== DANH MỤC ==========
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        parent_id INTEGER,
        description TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (parent_id) REFERENCES categories(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT
    )''')
    
    # ========== HÀNG HÓA ==========
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        barcode TEXT UNIQUE,
        name TEXT NOT NULL,
        warehouse_id INTEGER NOT NULL,
        category_id INTEGER,
        unit_id INTEGER,
        description TEXT,
        specifications TEXT,
    min_stock INTEGER DEFAULT 5,
    max_stock INTEGER DEFAULT 100,
        reorder_point INTEGER DEFAULT 0,
        cost_price REAL DEFAULT 0,
        selling_price REAL DEFAULT 0,
        tax_rate REAL DEFAULT 0,
        weight REAL DEFAULT 0,
        dimensions TEXT,
        image_url TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT,
        created_by INTEGER,
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (unit_id) REFERENCES units(id)
    )''')

    c.execute("SELECT COUNT(*) FROM company_profile WHERE id=1")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO company_profile
            (id, company_name, short_name, tax_code, phone, email, address, representative, website, bank_account, bank_name)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "An Tín Solution",
            "An Tín WMS",
            "",
            "",
            "info@antinsolution.com",
            "TP. Ho Chi Minh",
            "",
            "",
            "",
            ""
        ))

    # Insert default settings singleton
    c.execute("SELECT COUNT(*) FROM settings WHERE id=1")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO settings (id, allow_negative_stock)
            VALUES (1, 0)
        """)

    # Backward-compatible migration for older databases

    # Migration: Add ncc_debt_limit, kh_debt_limit to settings table
    c.execute("PRAGMA table_info(settings)")
    settings_columns = {row[1] for row in c.fetchall()}
    if "ncc_debt_limit" not in settings_columns:
        c.execute("ALTER TABLE settings ADD COLUMN ncc_debt_limit REAL DEFAULT 0")
    if "kh_debt_limit" not in settings_columns:
        c.execute("ALTER TABLE settings ADD COLUMN kh_debt_limit REAL DEFAULT 0")

    c.execute("PRAGMA table_info(products)")
    product_columns = {row[1] for row in c.fetchall()}
    if "discount_rate" not in product_columns:
        c.execute("ALTER TABLE products ADD COLUMN discount_rate REAL DEFAULT 0")
    if "discount_amount" not in product_columns:
        # Placeholder for future extensions; safe to ignore if not used
        pass
    if "warehouse_id" not in product_columns:
        # Add warehouse_id column and set default warehouse for existing products
        c.execute("ALTER TABLE products ADD COLUMN warehouse_id INTEGER")
        # Set default warehouse (first active warehouse) for existing products
        c.execute("SELECT id FROM warehouses WHERE is_active=1 LIMIT 1")
        default_wh = c.fetchone()
        if default_wh:
            c.execute("UPDATE products SET warehouse_id=? WHERE warehouse_id IS NULL", (default_wh['id'],))
        # Make it NOT NULL after setting defaults
        # Note: SQLite doesn't support ALTER COLUMN, so we recreate the table
        c.execute("SELECT id FROM warehouses WHERE is_active=1 LIMIT 1")
        default_wh = c.fetchone()
        if default_wh:
            c.execute('''
                CREATE TABLE IF NOT EXISTS products_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    barcode TEXT UNIQUE,
                    name TEXT NOT NULL,
                    warehouse_id INTEGER NOT NULL DEFAULT {},
                    category_id INTEGER,
                    unit_id INTEGER,
                    description TEXT,
                    specifications TEXT,
                    min_stock INTEGER DEFAULT 5,
                    max_stock INTEGER DEFAULT 100,
                    reorder_point INTEGER DEFAULT 0,
                    cost_price REAL DEFAULT 0,
                    selling_price REAL DEFAULT 0,
                    tax_rate REAL DEFAULT 0,
                    weight REAL DEFAULT 0,
                    dimensions TEXT,
                    image_url TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT,
                    created_by INTEGER,
                    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
                    FOREIGN KEY (category_id) REFERENCES categories(id),
                    FOREIGN KEY (unit_id) REFERENCES units(id)
                )
            '''.format(default_wh['id']))
            c.execute('''
                INSERT INTO products_new 
                SELECT id, code, barcode, name, 
                       COALESCE(warehouse_id, {}) as warehouse_id,
                       category_id, unit_id, description, specifications,
                       min_stock, max_stock, reorder_point, cost_price, selling_price,
                       tax_rate, weight, dimensions, image_url, is_active,
                       created_at, updated_at, created_by
                FROM products
            '''.format(default_wh['id']))
            c.execute("DROP TABLE products")
            c.execute("ALTER TABLE products_new RENAME TO products")
    
    # ========== VỊ TRÍ KHO ==========
    c.execute('''CREATE TABLE IF NOT EXISTS warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        address TEXT,
        manager_id INTEGER,
        phone TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (manager_id) REFERENCES users(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS warehouse_zones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        warehouse_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        UNIQUE(warehouse_id, code),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS warehouse_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        rack TEXT,
        shelf TEXT,
        bin TEXT,
        capacity REAL DEFAULT 0,
        current_load REAL DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        UNIQUE(zone_id, code),
        FOREIGN KEY (zone_id) REFERENCES warehouse_zones(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS product_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        quantity REAL DEFAULT 0,
        batch_number TEXT,
        expiry_date TEXT,
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(product_id, location_id, batch_number),
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (location_id) REFERENCES warehouse_locations(id)
    )''')
    
    # ========== KHÁCH HÀNG ==========
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        contact_person TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        district TEXT,
        city TEXT,
        tax_code TEXT,
        customer_type TEXT DEFAULT 'retail',  -- retail, wholesale, vip
        credit_limit REAL DEFAULT 0,
        current_debt REAL DEFAULT 0,
        discount_rate REAL DEFAULT 0,
        notes TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        created_by INTEGER
    )''')
    
    # ========== NHÀ CUNG CẤP ==========
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        contact_person TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        district TEXT,
        city TEXT,
        tax_code TEXT,
        bank_name TEXT,
        bank_account TEXT,
        payment_terms INTEGER DEFAULT 30,
        current_debt REAL DEFAULT 0,
        notes TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        created_by INTEGER
    )''')
    
    # ========== PHIẾU NHẬP KHO ==========
    c.execute('''CREATE TABLE IF NOT EXISTS import_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        supplier_id INTEGER,
        warehouse_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        expected_date TEXT,
        received_date TEXT,
        status TEXT DEFAULT 'draft',  -- draft, confirmed, partial, completed, cancelled
        total_amount REAL DEFAULT 0,
        discount_amount REAL DEFAULT 0,
        tax_amount REAL DEFAULT 0,
        final_amount REAL DEFAULT 0,
        paid_amount REAL DEFAULT 0,
        payment_status TEXT DEFAULT 'unpaid',  -- unpaid, partial, paid
        payment_method TEXT DEFAULT 'cash',
        reference_number TEXT,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT,
        created_by INTEGER,
        confirmed_by INTEGER,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS import_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        warehouse_id INTEGER,
        location_id INTEGER,
        quantity_ordered REAL DEFAULT 0,
        quantity_received REAL DEFAULT 0,
        unit_price REAL DEFAULT 0,
        discount_rate REAL DEFAULT 0,
        tax_rate REAL DEFAULT 0,
        total_price REAL DEFAULT 0,
        batch_number TEXT,
        expiry_date TEXT,
        notes TEXT,
        FOREIGN KEY (order_id) REFERENCES import_orders(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
        FOREIGN KEY (location_id) REFERENCES warehouse_locations(id)
    )''')
    
    # ========== PHIẾU XUẤT KHO ==========
    c.execute('''CREATE TABLE IF NOT EXISTS export_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        customer_id INTEGER,
        warehouse_id INTEGER NOT NULL,
        order_date TEXT NOT NULL,
        expected_date TEXT,
        shipped_date TEXT,
        status TEXT DEFAULT 'draft',  -- draft, confirmed, picking, shipped, completed, cancelled
        total_amount REAL DEFAULT 0,
        discount_amount REAL DEFAULT 0,
        tax_amount REAL DEFAULT 0,
        final_amount REAL DEFAULT 0,
        paid_amount REAL DEFAULT 0,
        payment_status TEXT DEFAULT 'unpaid',
        payment_method TEXT DEFAULT 'cash',
        shipping_address TEXT,
        shipping_method TEXT,
        shipping_fee REAL DEFAULT 0,
        reference_number TEXT,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT,
        created_by INTEGER,
        confirmed_by INTEGER,
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS export_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        warehouse_id INTEGER,
        location_id INTEGER,
        quantity_ordered REAL DEFAULT 0,
        quantity_shipped REAL DEFAULT 0,
        unit_price REAL DEFAULT 0,
        discount_rate REAL DEFAULT 0,
        tax_rate REAL DEFAULT 0,
        total_price REAL DEFAULT 0,
        batch_number TEXT,
        notes TEXT,
        FOREIGN KEY (order_id) REFERENCES export_orders(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
        FOREIGN KEY (location_id) REFERENCES warehouse_locations(id)
    )''')
    
# ========== TỒN KHO ==========
    
    # Migration: Add warehouse_id to import/export order_items if not exists, and populate from parent order
    for table in ['import_order_items', 'export_order_items']:
        c.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in c.fetchall()}
        if 'warehouse_id' not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN warehouse_id INTEGER")
            c.execute(f"""
                UPDATE {table} SET warehouse_id = (
                    SELECT o.warehouse_id FROM {table.replace('_items', '')} o 
                    WHERE o.id = {table}.order_id
                ) WHERE {table}.warehouse_id IS NULL
            """)
    
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        quantity_in_stock REAL DEFAULT 0,
        quantity_reserved REAL DEFAULT 0,
        quantity_available REAL DEFAULT 0,
        last_import_date TEXT,
        last_export_date TEXT,
        avg_cost_price REAL DEFAULT 0,
        total_value REAL DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(product_id, warehouse_id),  -- ✅ THÊM UNIQUE COMPOSITE KEY
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,  -- import, export, adjust, transfer
        reference_type TEXT,  -- import_order, export_order, adjustment
        reference_id INTEGER,
        quantity_change REAL NOT NULL,
        quantity_before REAL DEFAULT 0,
        quantity_after REAL DEFAULT 0,
        unit_price REAL DEFAULT 0,
        total_value REAL DEFAULT 0,
        batch_number TEXT,
        location_id INTEGER,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        created_by INTEGER,
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    )''')
    
    # ========== ĐIỀU CHỈNH KHO ==========
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_adjustments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        warehouse_id INTEGER NOT NULL,
        adjustment_date TEXT NOT NULL,
        reason TEXT,
        status TEXT DEFAULT 'draft',
        total_items INTEGER DEFAULT 0,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        created_by INTEGER,
        approved_by INTEGER,
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS adjustment_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adjustment_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        location_id INTEGER,
        quantity_system REAL DEFAULT 0,
        quantity_actual REAL DEFAULT 0,
        quantity_diff REAL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY (adjustment_id) REFERENCES inventory_adjustments(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    
    # ========== GÁN KHO CHO NGƯỜI DÙNG ==========
    c.execute('''CREATE TABLE IF NOT EXISTS user_warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        warehouse_id INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(user_id, warehouse_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE CASCADE
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sales_gps_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        accuracy REAL DEFAULT 0,
        address TEXT,
        note TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )''')
    
    # ========== CÔNG NỢ ==========
    c.execute('''CREATE TABLE IF NOT EXISTS debt_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_type TEXT NOT NULL,  -- 'customer', 'supplier'
        partner_id INTEGER NOT NULL,
        order_type TEXT NOT NULL,  -- 'import_order', 'export_order'
        order_id INTEGER,
        payment_date TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_method TEXT DEFAULT 'cash',
        reference_number TEXT,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        created_by INTEGER,
        FOREIGN KEY (created_by) REFERENCES users(id)
    )''')
    
    # ========== INDEXES ==========
    _create_indexes(c)
    
    conn.commit()
    
    # ========== DỮ LIỆU MẶC ĐỊNH ==========
    _insert_default_data(conn)
    
    # ========== MIGRATION: GÁN KHO MẶC ĐỊNH CHO NGƯỜI DÙNG HIỆN CÓ ==========
    _migrate_user_warehouses(conn)
    
    conn.close()


def _create_indexes(c):
    """Tạo INDEX để tăng hiệu năng truy vấn"""
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_active_warehouse ON products(is_active, warehouse_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_code ON products(code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inventory_product_warehouse ON inventory(product_id, warehouse_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inv_tx_product_wh_date ON inventory_transactions(product_id, warehouse_id, created_at)")
    
    # THÊM MỚI - indexes cho JOIN/WHERE thường gặp
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_unit_id ON products(unit_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inv_tx_type ON inventory_transactions(transaction_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_warehouses_active ON warehouses(is_active)")
    
    # THÊM MỚI - indexes cho ORDER BY và báo cáo phức tạp
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_created_at ON products(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inv_tx_wh_created ON inventory_transactions(warehouse_id, created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_inv_tx_wh_created_type ON inventory_transactions(warehouse_id, created_at, transaction_type)")
    
    # Index cho đơn nhập/xuất
    c.execute("CREATE INDEX IF NOT EXISTS idx_import_orders_date_status ON import_orders(order_date, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_orders_date_status ON export_orders(order_date, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_import_order_items_order ON import_order_items(order_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_order_items_order ON export_order_items(order_id)")
    
    # Covering indexes cho report subqueries (tránh table scan khi SUM trên subquery)
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_order_items_order_shipped ON export_order_items(order_id, quantity_shipped)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_import_order_items_order_received ON import_order_items(order_id, quantity_received, quantity_ordered)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_export_orders_date_status_wh ON export_orders(order_date, status, warehouse_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_import_orders_date_status_wh ON import_orders(order_date, status, warehouse_id)")
    


def _migrate_user_warehouses(conn):
    """Gán kho mặc định cho người dùng hiện có chưa có kho nào"""
    c = conn.cursor()
    c.execute("SELECT id FROM warehouses WHERE is_active=1 LIMIT 1")
    default_wh = c.fetchone()
    if not default_wh:
        conn.close()
        return
    default_wh_id = default_wh['id']
    
    # Lấy tất cả user non-admin chưa có kho nào
    c.execute("""
        SELECT u.id FROM users u
        LEFT JOIN user_warehouses uw ON u.id = uw.user_id
        WHERE u.role != 'admin' AND u.is_active = 1 AND uw.user_id IS NULL
    """)
    users_without_wh = c.fetchall()
    for user in users_without_wh:
        c.execute("""
            INSERT OR IGNORE INTO user_warehouses (user_id, warehouse_id)
            VALUES (?, ?)
        """, (user['id'], default_wh_id))
    
    conn.commit()


def _insert_default_data(conn):
    """Chèn dữ liệu mặc định"""
    c = conn.cursor()
    
    # Admin user
    c.execute("SELECT id FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute('''INSERT INTO users (username, password, full_name, email, role, is_active) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('admin', hash_password('admin123'), 'Quản trị viên', 'admin@antinsolution.com', 'admin', 1))
        
        c.execute('''INSERT INTO users (username, password, full_name, email, role, is_active) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('manager1', hash_password('manager123'), 'Nguyễn Văn A', 'manager@antinsolution.com', 'manager', 1))
        
        c.execute('''INSERT INTO users (username, password, full_name, email, role, is_active) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('staff1', hash_password('staff123'), 'Trần Thị B', 'staff@antinsolution.com', 'staff', 1))
    
    # Sellers (check independently)
    c.execute("SELECT id FROM users WHERE username='saler1'")
    if not c.fetchone():
        c.execute('''INSERT INTO users (username, password, full_name, email, role, is_active) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('saler1', hash_password('saler123'), 'Nguyễn Văn Sales', 'sales@antinsolution.com', 'saler', 1))
    
    c.execute("SELECT id FROM users WHERE username='saler2'")
    if not c.fetchone():
        c.execute('''INSERT INTO users (username, password, full_name, email, role, is_active) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  ('saler2', hash_password('saler123'), 'Trần Thị Sales', 'sales2@antinsolution.com', 'saler', 1))
    
    # Default permissions
    roles_permissions = {
        'admin': {'all': [1,1,1,1,1]},
        'manager': {
            'products': [1,1,1,0,1], 'customers': [1,1,1,0,1],
            'suppliers': [1,1,1,0,1], 'inventory': [1,1,1,0,1],
            'reports': [1,0,0,0,1], 'users': [1,0,0,0,0], 'settings': [1,0,0,0,0]
        },
        'staff': {
            'products': [1,0,0,0,0], 'customers': [1,1,1,0,0],
            'suppliers': [1,0,0,0,0], 'inventory': [1,1,0,0,0],
            'reports': [1,0,0,0,0], 'users': [0,0,0,0,0], 'settings': [0,0,0,0,0]
        },
        'viewer': {
            'products': [1,0,0,0,0], 'customers': [1,0,0,0,0],
            'suppliers': [1,0,0,0,0], 'inventory': [1,0,0,0,0],
            'reports': [1,0,0,0,0], 'users': [0,0,0,0,0], 'settings': [0,0,0,0,0]
        },
        'saler': {
            'products': [1,0,0,0,0],
            # Cho phép saler TẠO khách hàng mới, nhưng KHÔNG cho phép sửa/xóa
            'customers': [1,1,0,0,0],
            'suppliers': [1,0,0,0,0],
            'inventory': [1,0,0,0,0],
            'reports': [1,0,0,0,0],
            'users': [0,0,0,0,0],
            'settings': [0,0,0,0,0]
        }

    }
    
    modules = ['products', 'customers', 'suppliers', 'inventory', 'import_orders', 'export_orders', 'warehouses', 'reports', 'users', 'settings']
    
    for role, perms in roles_permissions.items():
        for module in modules:
            if 'all' in perms:
                p = perms['all']
            else:
                p = perms.get(module, [0,0,0,0,0])
            
            c.execute('''INSERT OR IGNORE INTO permissions 
                        (role, module, can_view, can_create, can_edit, can_delete, can_export)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (role, module, p[0], p[1], p[2], p[3], p[4]))
    
    # Units
    units = [('TUI', 'Túi'), ('BAO', 'Bao'), ('THUNG', 'Thùng'), 
             ('PCS', 'Cái/Chiếc'), ('BOX', 'Hộp'), ('KG', 'Kilogram'), 
             ('G', 'Gram'), ('L', 'Lít'), ('M', 'Mét'), ('M2', 'Mét vuông'),
             ('SET', 'Bộ'), ('ROLL', 'Cuộn'), ('PACK', 'Gói')]
    for code, name in units:
        c.execute("INSERT OR IGNORE INTO units (code, name) VALUES (?, ?)", (code, name))
    
    # Categories
    cats = [('GAO', 'Gạo', None),]
    for i, (code, name, parent) in enumerate(cats):
        c.execute("INSERT OR IGNORE INTO categories (code, name, parent_id) VALUES (?, ?, ?)",
                 (code, name, parent))
    
    # Default warehouses (2 warehouses)
    # Warehouse 1
    c.execute("SELECT id FROM warehouses WHERE code='KHO001'")
    wh1_row = c.fetchone()
    if not wh1_row:
        c.execute('''INSERT INTO warehouses (code, name, address, is_active) 
                     VALUES (?, ?, ?, ?)''',
                  ('KHO001', 'Kho chính', 'Xuân Hòa, Đồng Nai', 1))
        wh1_id = c.lastrowid
    else:
        wh1_id = wh1_row['id']
    
    # Zones for warehouse 1
    zones1 = [('A', 'Khu A - Hàng nhanh'), ('B', 'Khu B - Hàng chậm')]
    for code, name in zones1:
        c.execute("INSERT OR IGNORE INTO warehouse_zones (warehouse_id, code, name) VALUES (?, ?, ?)",
                 (wh1_id, code, name))
    
    c.execute("SELECT id FROM warehouse_zones WHERE warehouse_id=? AND code='A'", (wh1_id,))
    zone_a1 = c.fetchone()
    if zone_a1:
        # Locations for warehouse 1
        for shelf in ['01', '02']:
            for bin in ['A', 'B']:
                loc_code = f"A-{shelf}-{bin}"
                c.execute('''INSERT OR IGNORE INTO warehouse_locations 
                            (zone_id, code, name, rack, shelf, bin, capacity)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (zone_a1['id'], loc_code, f"Vị trí {loc_code}", 'A', shelf, bin, 100))
    
    # Warehouse 2
    c.execute("SELECT id FROM warehouses WHERE code='KHO002'")
    wh2_row = c.fetchone()
    if not wh2_row:
        c.execute('''INSERT INTO warehouses (code, name, address, is_active) 
                     VALUES (?, ?, ?, ?)''',
                  ('KHO002', 'Kho phụ', 'Quận 7, TP.HCM', 1))
        wh2_id = c.lastrowid
    else:
        wh2_id = wh2_row['id']
    
    # Zones for warehouse 2
    zones2 = [('A', 'Khu A - Hàng nhanh'), ('B', 'Khu B - Hàng chậm')]
    for code, name in zones2:
        c.execute("INSERT OR IGNORE INTO warehouse_zones (warehouse_id, code, name) VALUES (?, ?, ?)",
                 (wh2_id, code, name))
    
    c.execute("SELECT id FROM warehouse_zones WHERE warehouse_id=? AND code='A'", (wh2_id,))
    zone_a2 = c.fetchone()
    if zone_a2:
        # Locations for warehouse 2
        for shelf in ['01', '02']:
            for bin in ['A', 'B']:
                loc_code = f"A-{shelf}-{bin}"
                c.execute('''INSERT OR IGNORE INTO warehouse_locations 
                            (zone_id, code, name, rack, shelf, bin, capacity)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (zone_a2['id'], loc_code, f"Vị trí {loc_code}", 'A', shelf, bin, 100))
    
    # Sample products (1 product for each warehouse)
    c.execute("SELECT id FROM products WHERE code='GAO001'")
    if not c.fetchone():
        products = [
            ('GAO001', 'Gạo thơm ST25 (5Kg/Túi)', 1, 1, 0, 0, 0, 1),  # Warehouse 1
            ('GAO002', 'Gạo nếp cái hoa vàng (1Kg/Túi)', 1, 1, 0, 0, 0, 2),  # Warehouse 2
        ]
        for code, name, cat_id, unit_id, min_s, cost, sell, wh_id in products:
            c.execute('''INSERT OR IGNORE INTO products 
                        (code, name, category_id, unit_id, min_stock, cost_price, selling_price, warehouse_id, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)''',
                     (code, name, cat_id, unit_id, min_s, cost, sell, wh_id))
    
    # Sample customers
    c.execute("SELECT id FROM customers WHERE code='KH001'")
    if not c.fetchone():
        customers = [
            ('KH001', 'Công ty ABC', '0901234567', 'Quận 1, TP.HCM', 'wholesale'),
        ]
        for code, name, phone, addr, ctype in customers:
            c.execute('''INSERT OR IGNORE INTO customers (code, name, phone, address, customer_type, is_active)
                        VALUES (?, ?, ?, ?, ?, 1)''',
                     (code, name, phone, addr, ctype))
    
    # Sample suppliers
    c.execute("SELECT id FROM suppliers WHERE code='NCC001'")
    if not c.fetchone():
        suppliers = [
            ('NCC001', 'CÔNG TY CỔ PHẦN MÊ GẠO', '0973 978 039', 'Đường ĐT 852, Ấp Tân Lộc A, xã Tân Dương, Tỉnh Đồng Tháp, Việt Nam'),
        ]
        for code, name, phone, city in suppliers:
            c.execute('''INSERT OR IGNORE INTO suppliers (code, name, phone, city, is_active)
                        VALUES (?, ?, ?, ?, 1)''',
                     (code, name, phone, city))
    
    conn.commit()
    
    # Assign sellers to different warehouses
    c.execute("SELECT id FROM users WHERE username='saler1'")
    saler1 = c.fetchone()
    c.execute("SELECT id FROM users WHERE username='saler2'")
    saler2 = c.fetchone()
    
    if saler1 and saler2:
        saler1_id = saler1['id']
        saler2_id = saler2['id']
        
        # Get warehouse IDs
        c.execute("SELECT id FROM warehouses WHERE code='KHO001'")
        wh1_id = c.fetchone()
        c.execute("SELECT id FROM warehouses WHERE code='KHO002'")
        wh2_id = c.fetchone()
        
        if wh1_id and wh2_id:
            # Assign saler1 to warehouse 1
            c.execute('''INSERT OR IGNORE INTO user_warehouses (user_id, warehouse_id)
                        VALUES (?, ?)''',
                     (saler1_id, wh1_id['id']))
            
            # Assign saler2 to warehouse 2
            c.execute('''INSERT OR IGNORE INTO user_warehouses (user_id, warehouse_id)
                        VALUES (?, ?)''',
                     (saler2_id, wh2_id['id']))
            
            conn.commit()
