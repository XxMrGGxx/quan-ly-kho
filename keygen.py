# keygen_gui.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
from datetime import datetime
import csv
import threading

# Thêm thư mục hiện tại vào path để import được license_manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from license_manager import generate_offline_key, get_machine_id


class KeyGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Key Generator - An Tín WMS")
        self.root.geometry("900x750")
        self.root.resizable(True, True)
        
        # Thiết lập style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Màu sắc
        self.colors = {
            'primary': '#667eea',
            'secondary': '#764ba2',
            'success': '#10b981',
            'error': '#ef4444',
            'warning': '#f59e0b',
            'bg': '#f8f9fa'
        }
        
        # Tạo Notebook (tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: Tạo Key đơn
        self.single_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.single_tab, text='🔑 Tạo Key đơn')
        self.create_single_tab()
        
        # Tab 2: Tạo Key hàng loạt
        self.batch_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.batch_tab, text='📋 Tạo Key hàng loạt')
        self.create_batch_tab()
        
        # Tab 3: Lịch sử/Quản lý
        self.history_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.history_tab, text='📊 Lịch sử')
        self.create_history_tab()
        
        # Khởi tạo biến lưu key
        self.generated_keys = []
        self.current_key = None
        
    def create_single_tab(self):
        """Tạo giao diện tab tạo key đơn"""
        # Frame chính
        main_frame = ttk.Frame(self.single_tab, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill='x', pady=(0, 20))
        
        ttk.Label(header_frame, text="Tạo mã kích hoạt", 
                 font=('Arial', 18, 'bold')).pack(anchor='w')
        ttk.Label(header_frame, text="Nhập thông tin để tạo key cho khách hàng",
                 font=('Arial', 10)).pack(anchor='w')
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill='x', pady=10)
        
        # Form
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill='x', pady=10)
        
        # Machine ID
        ttk.Label(form_frame, text="Machine ID:", font=('Arial', 10, 'bold')).grid(
            row=0, column=0, sticky='w', pady=5)
        
        machine_frame = ttk.Frame(form_frame)
        machine_frame.grid(row=0, column=1, sticky='ew', pady=5, padx=(10, 0))
        machine_frame.columnconfigure(0, weight=1)
        
        self.machine_id_var = tk.StringVar()
        machine_entry = ttk.Entry(machine_frame, textvariable=self.machine_id_var, 
                                  font=('Courier', 10))
        machine_entry.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        
        btn_get_machine = ttk.Button(machine_frame, text="📥 Lấy máy hiện tại",
                                     command=self.get_current_machine)
        btn_get_machine.grid(row=0, column=1)
        
        ttk.Label(form_frame, text="(Để trống để sử dụng máy hiện tại)", 
                 font=('Arial', 8), foreground='gray').grid(
            row=1, column=1, sticky='w', padx=(10, 0))
        
        # Company
        ttk.Label(form_frame, text="Tên công ty:", font=('Arial', 10, 'bold')).grid(
            row=2, column=0, sticky='w', pady=5)
        self.company_var = tk.StringVar(value="An Tín Solution")
        company_entry = ttk.Entry(form_frame, textvariable=self.company_var, 
                                  font=('Arial', 10))
        company_entry.grid(row=2, column=1, sticky='ew', pady=5, padx=(10, 0))
        
        # Days
        ttk.Label(form_frame, text="Số ngày hết hạn:", font=('Arial', 10, 'bold')).grid(
            row=3, column=0, sticky='w', pady=5)
        self.days_var = tk.StringVar(value="365")
        days_spinbox = ttk.Spinbox(form_frame, from_=1, to=3650, 
                                   textvariable=self.days_var, width=20)
        days_spinbox.grid(row=3, column=1, sticky='w', pady=5, padx=(10, 0))
        
        # Users
        ttk.Label(form_frame, text="Số user tối đa:", font=('Arial', 10, 'bold')).grid(
            row=4, column=0, sticky='w', pady=5)
        self.users_var = tk.StringVar(value="50")
        users_spinbox = ttk.Spinbox(form_frame, from_=1, to=999, 
                                   textvariable=self.users_var, width=20)
        users_spinbox.grid(row=4, column=1, sticky='w', pady=5, padx=(10, 0))
        
        # Configure grid
        form_frame.columnconfigure(1, weight=1)
        
        # Button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=20)
        
        self.generate_btn = ttk.Button(btn_frame, text="🚀 Tạo Key", 
                                      command=self.generate_key_thread,
                                      style='Accent.TButton')
        self.generate_btn.pack(side='left', padx=(0, 10))
        
        self.clear_btn = ttk.Button(btn_frame, text="🗑️ Xóa kết quả",
                                   command=self.clear_result)
        self.clear_btn.pack(side='left')
        
        # Result frame
        self.result_frame = ttk.LabelFrame(main_frame, text="Kết quả", padding="15")
        self.result_frame.pack(fill='both', expand=True, pady=10)
        
        # Result content
        self.result_text = scrolledtext.ScrolledText(self.result_frame, 
                                                     height=15, wrap=tk.WORD,
                                                     font=('Courier', 10))
        self.result_text.pack(fill='both', expand=True)
        self.result_text.config(state='disabled')
        
        # Status bar
        self.status_var = tk.StringVar(value="Sẵn sàng")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, 
                               relief='sunken', anchor='w')
        status_bar.pack(fill='x', pady=(10, 0))
        
    def create_batch_tab(self):
        """Tạo giao diện tab tạo key hàng loạt"""
        main_frame = ttk.Frame(self.batch_tab, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Header
        ttk.Label(main_frame, text="Tạo Key hàng loạt", 
                 font=('Arial', 18, 'bold')).pack(anchor='w')
        ttk.Label(main_frame, text="Tải lên file CSV để tạo nhiều key cùng lúc",
                 font=('Arial', 10)).pack(anchor='w', pady=(0, 10))
        
        # Instructions
        info_frame = ttk.LabelFrame(main_frame, text="📋 Hướng dẫn", padding="10")
        info_frame.pack(fill='x', pady=10)
        
        instructions = """
        File CSV format: machine_id,company,days,users
        Ví dụ:
        ANTIN-D4890898-F812AD7A,An Tín Solution,365,50
        ANTIN-AABBCCDD-EEFFGGHH,Công ty ABC,180,20
        """
        ttk.Label(info_frame, text=instructions, font=('Courier', 9)).pack(anchor='w')
        
        # Upload frame
        upload_frame = ttk.Frame(main_frame)
        upload_frame.pack(fill='x', pady=20)
        
        self.file_path_var = tk.StringVar()
        ttk.Label(upload_frame, text="Chọn file CSV:").pack(anchor='w')
        
        file_select_frame = ttk.Frame(upload_frame)
        file_select_frame.pack(fill='x', pady=5)
        
        ttk.Entry(file_select_frame, textvariable=self.file_path_var, 
                 state='readonly').pack(side='left', fill='x', expand=True, padx=(0, 10))
        
        ttk.Button(file_select_frame, text="📂 Chọn file", 
                  command=self.select_csv_file).pack(side='left')
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=10)
        
        self.batch_generate_btn = ttk.Button(btn_frame, text="🚀 Tạo Key hàng loạt",
                                            command=self.batch_generate_thread)
        self.batch_generate_btn.pack(side='left', padx=(0, 10))
        
        self.batch_clear_btn = ttk.Button(btn_frame, text="🗑️ Xóa kết quả",
                                         command=self.clear_batch_result)
        self.batch_clear_btn.pack(side='left')
        
        # Result
        self.batch_result_frame = ttk.LabelFrame(main_frame, text="Kết quả", padding="15")
        self.batch_result_frame.pack(fill='both', expand=True, pady=10)
        
        self.batch_result_text = scrolledtext.ScrolledText(self.batch_result_frame, 
                                                          height=15, wrap=tk.WORD,
                                                          font=('Courier', 9))
        self.batch_result_text.pack(fill='both', expand=True)
        self.batch_result_text.config(state='disabled')
        
        # Status
        self.batch_status_var = tk.StringVar(value="Sẵn sàng")
        batch_status = ttk.Label(main_frame, textvariable=self.batch_status_var,
                                relief='sunken', anchor='w')
        batch_status.pack(fill='x', pady=(10, 0))
        
    def create_history_tab(self):
        """Tạo tab lịch sử"""
        main_frame = ttk.Frame(self.history_tab, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        ttk.Label(main_frame, text="Lịch sử tạo Key", 
                 font=('Arial', 18, 'bold')).pack(anchor='w')
        ttk.Label(main_frame, text="Danh sách các key đã tạo trong phiên làm việc",
                 font=('Arial', 10)).pack(anchor='w', pady=(0, 20))
        
        # Treeview
        columns = ('STT', 'Machine ID', 'Công ty', 'Key', 'Ngày tạo')
        self.history_tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=12)
        
        # Define headings
        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=100)
        
        self.history_tree.column('Machine ID', width=180)
        self.history_tree.column('Công ty', width=150)
        self.history_tree.column('Key', width=200)
        self.history_tree.column('Ngày tạo', width=150)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient='vertical', 
                                 command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        
        self.history_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text="🗑️ Xóa lịch sử", 
                  command=self.clear_history).pack(side='left')
        ttk.Button(btn_frame, text="💾 Xuất CSV", 
                  command=self.export_history).pack(side='left', padx=(10, 0))
        
    def get_current_machine(self):
        """Lấy machine ID của máy hiện tại"""
        try:
            machine_id = get_machine_id()
            self.machine_id_var.set(machine_id)
            self.status_var.set(f"✅ Đã lấy Machine ID: {machine_id}")
            messagebox.showinfo("Thành công", f"Đã lấy Machine ID:\n{machine_id}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lấy Machine ID:\n{str(e)}")
            self.status_var.set(f"❌ Lỗi: {str(e)}")
    
    def machine_id_to_fingerprint(self, machine_id):
        """Chuyển đổi Machine ID sang fingerprint"""
        parts = machine_id.strip().upper().replace(' ', '').split('-')
        
        if len(parts) == 3 and parts[0] == 'ANTIN':
            fp_prefix = parts[1] + parts[2]
            if len(fp_prefix) == 16 and all(c in '0123456789ABCDEF' for c in fp_prefix):
                return fp_prefix.lower() + '0' * 48
        
        raise ValueError(f"Machine ID không hợp lệ: {machine_id}")
    
    def generate_key_thread(self):
        """Tạo key trong thread riêng để không đóng băng UI"""
        thread = threading.Thread(target=self.generate_key)
        thread.daemon = True
        thread.start()
    
    def generate_key(self):
        """Tạo key đơn"""
        # Disable button
        self.root.after(0, lambda: self.generate_btn.config(state='disabled'))
        self.root.after(0, lambda: self.status_var.set("⏳ Đang tạo key..."))
        
        try:
            machine_id = self.machine_id_var.get().strip()
            company = self.company_var.get().strip()
            days = int(self.days_var.get())
            users = int(self.users_var.get())
            
            # Validate
            if days < 1:
                raise ValueError("Số ngày phải lớn hơn 0")
            if users < 1:
                raise ValueError("Số user phải lớn hơn 0")
            
            # Xác định fingerprint
            if machine_id:
                fingerprint = self.machine_id_to_fingerprint(machine_id)
            else:
                    machine_id = get_machine_id()
            
            # Tạo activation key với đầy đủ thông tin
            activation_key = generate_offline_key(fingerprint, company, days, users)
            
            # Lưu key
            key_info = {
                'machine_id': machine_id,
                'company': company,
                'days': days,
                'users': users,
                'activation_key': activation_key,
                'created_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            }
            self.current_key = key_info
            self.generated_keys.append(key_info)
            
            # Hiển thị kết quả
            self.root.after(0, lambda: self.display_result(key_info))
            self.root.after(0, lambda: self.add_to_history(key_info))
            self.root.after(0, lambda: self.status_var.set("✅ Tạo key thành công!"))
            
        except ValueError as e:
            error_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("Lỗi", error_msg))
            self.root.after(0, lambda: self.status_var.set(f"❌ Lỗi: {error_msg}"))
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Lỗi tạo key:\n{error_msg}"))
            self.root.after(0, lambda: self.status_var.set(f"❌ Lỗi: {error_msg}"))
        finally:
            self.root.after(0, lambda: self.generate_btn.config(state='normal'))
    
    def display_result(self, key_info):
        """Hiển thị kết quả trong text widget"""
        self.result_text.config(state='normal')
        self.result_text.delete(1.0, tk.END)
        
        result = f"""
{'═' * 60}
  🔑 MÃ KÍCH HOẠT - AN TÍN WMS
{'═' * 60}

  Machine ID:    {key_info['machine_id']}
  Công ty:       {key_info['company']}
  Hạn sử dụng:   {key_info['days']} ngày
  Số user tối đa: {key_info['users']} user

  {'═' * 40}
  ❚  {key_info['activation_key']}  ❚
  {'═' * 40}

  📝 Hướng dẫn:
  1. Gửi mã này cho khách hàng có Machine ID: {key_info['machine_id']}
  2. Khách hàng vào menu "Bản quyền" -> nhập mã kích hoạt
  3. Key chỉ hoạt động trên đúng máy có Machine ID này

  📅 Ngày tạo: {key_info['created_at']}
{'═' * 60}
"""
        self.result_text.insert(1.0, result)
        self.result_text.config(state='disabled')
    
    def clear_result(self):
        """Xóa kết quả hiển thị"""
        self.result_text.config(state='normal')
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(state='disabled')
        self.current_key = None
        self.status_var.set("Đã xóa kết quả")
    
    def select_csv_file(self):
        """Chọn file CSV"""
        file_path = filedialog.askopenfilename(
            title="Chọn file CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.batch_status_var.set(f"✅ Đã chọn file: {os.path.basename(file_path)}")
    
    def batch_generate_thread(self):
        """Tạo key hàng loạt trong thread riêng"""
        thread = threading.Thread(target=self.batch_generate)
        thread.daemon = True
        thread.start()
    
    def batch_generate(self):
        """Tạo key hàng loạt từ file CSV"""
        file_path = self.file_path_var.get()
        
        if not file_path:
            self.root.after(0, lambda: messagebox.showwarning("Cảnh báo", "Vui lòng chọn file CSV!"))
            return
        
        if not os.path.exists(file_path):
            self.root.after(0, lambda: messagebox.showerror("Lỗi", "File không tồn tại!"))
            return
        
        # Disable button
        self.root.after(0, lambda: self.batch_generate_btn.config(state='disabled'))
        self.root.after(0, lambda: self.batch_status_var.set("⏳ Đang xử lý..."))
        
        try:
            results = []
            errors = []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for line_num, row in enumerate(reader, 1):
                    if not row or all(cell.strip() == '' for cell in row):
                        continue
                    
                    if len(row) < 1:
                        continue
                    
                    machine_id = row[0].strip()
                    company = row[1].strip() if len(row) > 1 else 'An Tín Solution'
                    days = int(row[2]) if len(row) > 2 and row[2].strip().isdigit() else 365
                    users = int(row[3]) if len(row) > 3 and row[3].strip().isdigit() else 50
                    
                    try:
                        fingerprint = self.machine_id_to_fingerprint(machine_id)
                        key = generate_offline_key(fingerprint, company, days, users)
                        results.append({
                            'machine_id': machine_id,
                            'company': company,
                            'days': days,
                            'users': users,
                            'activation_key': key
                        })
                        # Lưu vào lịch sử
                        key_info = {
                            'machine_id': machine_id,
                            'company': company,
                            'days': days,
                            'users': users,
                            'activation_key': key,
                            'created_at': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                        }
                        self.generated_keys.append(key_info)
                        self.root.after(0, lambda k=key_info: self.add_to_history(k))
                    except ValueError as e:
                        errors.append(f"Dòng {line_num}: {e}")
            
            # Hiển thị kết quả
            self.root.after(0, lambda: self.display_batch_result(results, errors))
            self.root.after(0, lambda: self.batch_status_var.set(f"✅ Đã tạo {len(results)} keys"))
            
            if errors:
                self.root.after(0, lambda: messagebox.showwarning("Cảnh báo", 
                    f"Tạo thành công {len(results)} keys\nCó {len(errors)} lỗi:\n\n" + "\n".join(errors[:5])))
            else:
                self.root.after(0, lambda: messagebox.showinfo("Thành công", 
                    f"Đã tạo thành công {len(results)} keys!"))
                
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("Lỗi", f"Lỗi xử lý file:\n{error_msg}"))
            self.root.after(0, lambda: self.batch_status_var.set(f"❌ Lỗi: {error_msg}"))
        finally:
            self.root.after(0, lambda: self.batch_generate_btn.config(state='normal'))
    
    def display_batch_result(self, results, errors):
        """Hiển thị kết quả batch"""
        self.batch_result_text.config(state='normal')
        self.batch_result_text.delete(1.0, tk.END)
        
        output = f"""
{'═' * 60}
  📋 KẾT QUẢ TẠO KEY HÀNG LOẠT
{'═' * 60}

  Tổng số key tạo thành công: {len(results)}
  Số lỗi: {len(errors)}

{'═' * 60}
"""
        
        if results:
            output += "\n  ✅ DANH SÁCH KEY:\n\n"
            for i, r in enumerate(results, 1):
                output += f"  {i}. Machine ID: {r['machine_id']}\n"
                output += f"     Công ty: {r['company']}\n"
                output += f"     Key: {r['activation_key']}\n"
                output += f"     Hạn: {r['days']} ngày - User: {r['users']}\n\n"
        
        if errors:
            output += "\n  ❌ DANH SÁCH LỖI:\n\n"
            for error in errors:
                output += f"  - {error}\n"
        
        output += f"\n{'═' * 60}"
        
        self.batch_result_text.insert(1.0, output)
        self.batch_result_text.config(state='disabled')
    
    def clear_batch_result(self):
        """Xóa kết quả batch"""
        self.batch_result_text.config(state='normal')
        self.batch_result_text.delete(1.0, tk.END)
        self.batch_result_text.config(state='disabled')
        self.file_path_var.set("")
        self.batch_status_var.set("Đã xóa kết quả")
    
    def add_to_history(self, key_info):
        """Thêm key vào lịch sử"""
        try:
            # Kiểm tra xem key đã tồn tại chưa
            existing = self.history_tree.get_children()
            for item in existing:
                values = self.history_tree.item(item, 'values')
                if values and values[3] == key_info['activation_key']:
                    return
            
            # Thêm mới
            self.history_tree.insert('', 'end', values=(
                len(self.generated_keys),
                key_info['machine_id'],
                key_info['company'],
                key_info['activation_key'],
                key_info['created_at']
            ))
        except Exception as e:
            print(f"Lỗi thêm lịch sử: {e}")
    
    def clear_history(self):
        """Xóa lịch sử"""
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn xóa tất cả lịch sử?"):
            self.history_tree.delete(*self.history_tree.get_children())
            self.generated_keys = []
    
    def export_history(self):
        """Xuất lịch sử ra file CSV"""
        if not self.generated_keys:
            messagebox.showwarning("Cảnh báo", "Không có dữ liệu để xuất!")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Lưu file CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['STT', 'Machine ID', 'Công ty', 'Key', 'Ngày tạo'])
                    for i, key in enumerate(self.generated_keys, 1):
                        writer.writerow([
                            i,
                            key['machine_id'],
                            key['company'],
                            key['activation_key'],
                            key['created_at']
                        ])
                messagebox.showinfo("Thành công", f"Đã xuất lịch sử ra file:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể xuất file:\n{str(e)}")


def main():
    root = tk.Tk()
    
    # Set icon (nếu có)
    try:
        root.iconbitmap(default='icon.ico')
    except:
        pass
    
    # Tạo ứng dụng
    KeyGeneratorApp(root)
    
    # Center window
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    # Run
    root.mainloop()


if __name__ == '__main__':
    main()