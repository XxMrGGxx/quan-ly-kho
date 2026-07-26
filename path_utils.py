"""
Utility để xác định thư mục làm việc khi chạy dưới dạng script thường hoặc
PyInstaller bundle (onedir).

Có 2 loại đường dẫn khác nhau:
  1. get_app_dir()     → thư mục chứa dữ liệu người dùng (data/), nằm cạnh file exe
  2. get_resources_dir() → thư mục chứa static/templates khi build (in _internal/ onedir)
"""
import sys
from pathlib import Path


def _resolve_app_dir() -> Path:
    """
    Thư mục gốc của ứng dụng - nơi chứa dữ liệu người dùng (data/*).
    - Khi chạy script thường: thư mục chứa file Python chính
    - Khi chạy PyInstaller onedir: thư mục chứa file .exe (bên cạnh _internal/)
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller onedir: sys.executable là file .exe
        exe_path = Path(sys.executable).resolve()
        return exe_path.parent
    else:
        # Chạy script thường: thư mục chứa file này
        return Path(__file__).resolve().parent


def _resolve_resources_dir() -> Path:
    """
    Thư mục chứa tài nguyên tĩnh (static/, templates/).
    - Khi chạy script thường: giống get_app_dir()
    - Khi chạy PyInstaller onedir: sys._MEIPASS (thư mục _internal/)
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller onedir: thư mục _internal/ chứa static/, templates/
        return Path(sys._MEIPASS).resolve()
    else:
        return Path(__file__).resolve().parent


# Singleton cache
_APP_DIR = None
_RESOURCES_DIR = None


def get_app_dir() -> Path:
    """Thư mục lưu dữ liệu người dùng (data/, cạnh exe)."""
    global _APP_DIR
    if _APP_DIR is None:
        _APP_DIR = _resolve_app_dir()
    return _APP_DIR


def get_resources_dir() -> Path:
    """Thư mục chứa tài nguyên tĩnh (static/, templates/)."""
    global _RESOURCES_DIR
    if _RESOURCES_DIR is None:
        _RESOURCES_DIR = _resolve_resources_dir()
    return _RESOURCES_DIR