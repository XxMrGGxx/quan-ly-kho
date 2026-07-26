"""
WMS Running Overlay - Hiển thị khung "WMS Running" góc trên bên trái màn hình
"""
import tkinter as tk
import threading


class WMSOverlay:
    """Cửa sổ Tkinter không titlebar, cố định góc trên bên trái, hiển thị 'WMS Running'."""

    def __init__(self, text="QL Kho đang chạy", bg_color="#185d11", fg_color="white", font_size=10):
        self.text = text
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.font_size = font_size
        self.root = None

    def _build(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # Ẩn title bar
        self.root.attributes("-topmost", True)  # Luôn ở trên cùng
        self.root.attributes("-alpha", 0.85)  # Hơi trong suốt

        # Label hiển thị text
        label = tk.Label(
            self.root,
            text=self.text,
            bg=self.bg_color,
            fg=self.fg_color,
            font=("Segoe UI", self.font_size, "bold"),
            padx=12,
            pady=6,
        )
        label.pack()

        # Cập nhật layout để lấy kích thước thực
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()

        # Đặt cửa sổ ở góc trên bên trái (x=0, y=0)
        self.root.geometry(f"{w}x{h}+0+0")

        # Không cho phép resize
        self.root.resizable(False, False)

    def show(self):
        """Hiển thị overlay (chạy trong thread riêng)."""
        self._build()
        self.root.mainloop()

    def close(self):
        """Đóng overlay."""
        if self.root:
            self.root.quit()
            self.root.destroy()


# Hàm tiện ích để chạy overlay trong luồng riêng
def run_overlay():
    """Khởi tạo và chạy WMSOverlay trong main thread của Tkinter."""
    overlay = WMSOverlay()
    overlay.show()


def start_overlay_thread():
    """Khởi động overlay trong một thread riêng (dùng để gọi từ main.py)."""
    t = threading.Thread(target=run_overlay, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    # Test khi chạy trực tiếp file này
    run_overlay()