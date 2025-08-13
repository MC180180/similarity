import tkinter as tk
from tkinter import filedialog
import threading


selected_folders = []
image_groups = []

def select_folders():
    """使用Tkinter选择文件夹"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 将窗口置顶
    root.attributes('-topmost', True)
    
    # 强制窗口获取焦点
    root.focus_force()
    
    # 将窗口提升到最前面
    root.lift()
    
    folder_paths = filedialog.askdirectory(
        title='选择包含图片的文件夹',
        mustexist=True,
        parent=root  # 指定父窗口
    )
    
    if folder_paths:
        # 将选中的文件夹路径添加到全局变量中
        if folder_paths not in selected_folders:
            selected_folders.append(folder_paths)
    
    root.destroy()
    return folder_paths

def open_folder_dialog():
    """在单独的线程中打开文件夹选择对话框"""
    thread = threading.Thread(target=select_folders)
    thread.daemon = True
    thread.start()

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS