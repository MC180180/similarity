import sys
import os
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QProgressBar, QScrollArea, 
                             QGridLayout, QSpinBox, QDoubleSpinBox, QFormLayout, QLineEdit,
                             QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QFont, QIcon, QIntValidator
from PIL import Image
import imagehash

# ==============================================================================
#  色彩和样式配置 (无变化)
# ==============================================================================
class AppTheme:
    COLOR_BACKGROUND = "#FBFBFB"
    COLOR_SECONDARY = "#E8F9FF"
    COLOR_PRIMARY = "#C4D9FF"
    COLOR_ACCENT = "#C5BAFF"
    COLOR_TEXT = "#2c3e50"
    COLOR_BEST_BG = "#E8F9FF"
    COLOR_SELECTED_BORDER = "#C5BAFF"

    STYLESHEET = f"""
        QMainWindow, QWidget {{
            background-color: {COLOR_BACKGROUND};
            color: {COLOR_TEXT};
            font-family: "Segoe UI", "Microsoft YaHei";
            font-size: 14px;
        }}
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: {COLOR_TEXT};
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: #B0A5F7;
        }}
        QPushButton:disabled {{
            background-color: #E0E0E0;
            color: #A0A0A0;
        }}
        QLabel#TitleLabel {{
            font-size: 18px;
            font-weight: bold;
        }}
        QProgressBar {{
            border: 1px solid {COLOR_PRIMARY};
            border-radius: 5px;
            text-align: center;
            background-color: white;
            color: {COLOR_TEXT};
        }}
        QProgressBar::chunk {{
            background-color: {COLOR_ACCENT};
            border-radius: 4px;
        }}
        QScrollArea {{
            border: 1px solid {COLOR_PRIMARY};
            border-radius: 5px;
        }}
        QFrame#GroupFrame {{
            border: 1px solid {COLOR_PRIMARY};
            border-radius: 5px;
            margin-bottom: 10px;
        }}
        QSpinBox, QDoubleSpinBox, QLineEdit {{
            padding: 5px;
            border: 1px solid {COLOR_PRIMARY};
            border-radius: 5px;
        }}
    """

# ==============================================================================
#  图片处理逻辑 (无变化)
# ==============================================================================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_hashes_for_image(path, hash_size):
    try:
        img = Image.open(path).convert('L')
        phash = imagehash.phash(img, hash_size=hash_size)
        ahash = imagehash.average_hash(img, hash_size=hash_size)
        dhash = imagehash.dhash(img, hash_size=hash_size)
        return path, (phash, ahash, dhash)
    except Exception:
        return path, (None, None, None)

def calculate_similarity(hash1, hash2):
    if not hash1 or not hash2: return 0
    distance = hash1 - hash2
    max_bits = len(str(hash1)) * 4
    return (1 - distance / max_bits) * 100

def get_best_image_in_group(group):
    if not group: return None
    try:
        return max(group, key=lambda p: os.path.getsize(p) * Image.open(p).size[0] * Image.open(p).size[1])
    except (FileNotFoundError, OSError):
        return group[0]

# ==============================================================================
#  *** 核心修改：性能优化的多线程 Worker ***
# ==============================================================================
class Worker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)

    def __init__(self, folder_paths, threshold, hash_size):
        super().__init__()
        self.folder_paths = folder_paths
        self.threshold = threshold
        self.hash_size = hash_size
        self.is_running = True
        self.max_workers = os.cpu_count() or 4

    def run(self):
        # --- 阶段1: 收集图片路径 ---
        image_paths = []
        for folder_path in self.folder_paths:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if allowed_file(file):
                        image_paths.append(os.path.join(root, file))
        
        total_images = len(image_paths)
        if total_images < 2:
            self.finished.emit([])
            return

        # --- 阶段2: 并行计算哈希值 ---
        self.progress.emit(0, f"阶段 1/3: 正在并行计算 {total_images} 张图片的哈希值...")
        hashes = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(calculate_hashes_for_image, path, self.hash_size) for path in image_paths]
            for i, future in enumerate(as_completed(futures)):
                if not self.is_running: return
                path, hash_tuple = future.result()
                hashes[path] = hash_tuple
                self.progress.emit(int((i + 1) / total_images * 40), f"计算哈希: {os.path.basename(path)}")

        # --- 阶段3: 优化后的相似度比较 ---
        self.progress.emit(40, "阶段 2/3: 正在比较图片相似度...")
        similar_pairs = []
        
        # *** 性能优化：预先计算最大允许的哈希距离 ***
        # 只有当两张图片的phash距离小于这个值时，我们才进行完整的比较
        max_phash_dist = int((self.hash_size**2) * (1 - (self.threshold - 10) / 100))

        total_comparisons = total_images * (total_images - 1) // 2
        completed_comparisons = 0

        # 使用单线程循环，但内部进行快速预检，这样更容易报告进度
        for i in range(total_images):
            if not self.is_running: return
            path1 = image_paths[i]
            phash1, ahash1, dhash1 = hashes.get(path1, (None, None, None))
            if not phash1: continue

            for j in range(i + 1, total_images):
                completed_comparisons += 1
                if completed_comparisons % 50 == 0: # 更频繁地更新进度
                    self.progress.emit(40 + int(completed_comparisons / total_comparisons * 50), f"阶段 2/3: 比较中... ({completed_comparisons}/{total_comparisons})")

                path2 = image_paths[j]
                phash2, ahash2, dhash2 = hashes.get(path2, (None, None, None))
                if not phash2: continue

                # *** 性能优化：快速预检 ***
                if (phash1 - phash2) > max_phash_dist:
                    continue

                # 只有通过了快速预检的图片对，才进行完整计算
                phash_sim = calculate_similarity(phash1, phash2)
                ahash_sim = calculate_similarity(ahash1, ahash2)
                dhash_sim = calculate_similarity(dhash1, dhash2)
                combined_sim = (phash_sim * 0.5 + ahash_sim * 0.3 + dhash_sim * 0.2)
                
                if combined_sim >= self.threshold:
                    similar_pairs.append((path1, path2))

        # --- 阶段4: 合并相似对为组 ---
        self.progress.emit(90, "阶段 3/3: 正在合并相似组...")
        similarity_groups = self.group_similar_pairs(similar_pairs)
        
        self.progress.emit(100, "处理完成！")
        self.finished.emit(similarity_groups)

    def group_similar_pairs(self, similar_pairs):
        graph = {}
        for p1, p2 in similar_pairs:
            graph.setdefault(p1, set()).add(p2)
            graph.setdefault(p2, set()).add(p1)

        groups = []
        visited = set()
        for node in graph:
            if node not in visited:
                current_group = set()
                stack = [node]
                while stack:
                    current_node = stack.pop()
                    if current_node not in visited:
                        visited.add(current_node)
                        current_group.add(current_node)
                        stack.extend(graph.get(current_node, set()) - visited)
                if len(current_group) > 1:
                    groups.append(list(current_group))
        return groups

    def stop(self):
        self.is_running = False

# ==============================================================================
#  自定义图片控件 (无变化)
# ==============================================================================
class ImageWidget(QWidget):
    def __init__(self, img_path, is_best):
        super().__init__()
        self.img_path = img_path
        self.is_best = is_best
        self.is_selected = False

        self.setFixedSize(220, 260)
        
        layout = QVBoxLayout(self)
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setFixedSize(200, 200)
        
        try:
            pixmap = QPixmap(img_path)
            self.img_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception as e:
            self.img_label.setText("无法加载图片")

        self.info_label = QLabel(os.path.basename(img_path))
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.img_label)
        layout.addWidget(self.info_label)

        self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet(f"border: 2px solid {AppTheme.COLOR_SELECTED_BORDER}; border-radius: 5px; background-color: {AppTheme.COLOR_PRIMARY};")
        elif self.is_best:
            self.setStyleSheet(f"border: 2px solid #27ae60; border-radius: 5px; background-color: {AppTheme.COLOR_BEST_BG};")
        else:
            self.setStyleSheet("border: 1px solid #CCCCCC; border-radius: 5px; background-color: white;")

    def mousePressEvent(self, event):
        self.set_selected(not self.is_selected)
        super().mousePressEvent(event)

    def set_selected(self, selected):
        self.is_selected = selected
        self.update_style()

# ==============================================================================
#  主窗口 GUI (无变化)
# ==============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片比较器")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(AppTheme.STYLESHEET)
        
        self.selected_folders = []
        self.image_groups = []
        self.image_widgets = []

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        controls_layout = QHBoxLayout()
        
        self.select_folder_btn = QPushButton("选择文件夹")
        self.select_folder_btn.clicked.connect(self.select_folders)
        
        self.start_btn = QPushButton("开始处理")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setEnabled(False)

        self.folder_label = QLabel("尚未选择文件夹")
        self.folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        params_layout = QFormLayout()
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(1, 100); self.threshold_spin.setValue(80.0); self.threshold_spin.setSuffix(" %")
        
        self.hash_size_edit = QLineEdit()
        self.hash_size_edit.setText("8")
        self.hash_size_edit.setValidator(QIntValidator(2, 9999, self))
        
        params_layout.addRow("相似度阈值:", self.threshold_spin)
        params_layout.addRow("哈希大小:", self.hash_size_edit)

        controls_layout.addWidget(self.select_folder_btn)
        controls_layout.addWidget(self.folder_label, 1)
        controls_layout.addLayout(params_layout)
        controls_layout.addWidget(self.start_btn)
        
        main_layout.addLayout(controls_layout)

        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("请先选择一个或多个文件夹")
        progress_layout.addWidget(self.status_label, 1)
        progress_layout.addWidget(self.progress_bar, 1)
        main_layout.addLayout(progress_layout)

        self.results_actions_widget = QWidget()
        results_actions_layout = QHBoxLayout(self.results_actions_widget)
        results_actions_layout.setContentsMargins(0, 0, 0, 0)
        
        self.select_all_btn = QPushButton("全选所有")
        self.select_all_btn.clicked.connect(self.select_all)
        
        self.auto_select_btn = QPushButton("自动保留最优")
        self.auto_select_btn.clicked.connect(self.auto_select)
        
        self.delete_btn = QPushButton("删除选中图片")
        self.delete_btn.clicked.connect(self.delete_selected)
        
        results_actions_layout.addWidget(self.select_all_btn)
        results_actions_layout.addWidget(self.auto_select_btn)
        results_actions_layout.addStretch()
        results_actions_layout.addWidget(self.delete_btn)
        main_layout.addWidget(self.results_actions_widget)
        self.results_actions_widget.setVisible(False)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.scroll_area.setWidget(self.results_container)
        main_layout.addWidget(self.scroll_area)

    def select_folders(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder and folder not in self.selected_folders:
            self.selected_folders.append(folder)
            self.folder_label.setText("; ".join(f"...{folder[-30:]}" for folder in self.selected_folders))
            self.start_btn.setEnabled(True)

    def start_processing(self):
        self.start_btn.setEnabled(False); self.select_folder_btn.setEnabled(False)
        self.results_actions_widget.setVisible(False)
        self.image_widgets.clear()

        for i in reversed(range(self.results_layout.count())): 
            widget_to_remove = self.results_layout.itemAt(i).widget()
            widget_to_remove.setParent(None)
            widget_to_remove.deleteLater()

        try:
            hash_size = int(self.hash_size_edit.text())
        except (ValueError, TypeError):
            hash_size = 8
            self.hash_size_edit.setText("8")

        self.worker = Worker(self.selected_folders, self.threshold_spin.value(), hash_size)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.show_results)
        self.worker.start()

    def update_progress(self, value, status):
        self.progress_bar.setValue(value); self.status_label.setText(status)

    def show_results(self, groups):
        self.image_groups = sorted(groups, key=len, reverse=True)
        if not self.image_groups:
            self.status_label.setText("处理完成，未找到相似的图片组。")
        else:
            self.status_label.setText(f"处理完成！找到 {len(self.image_groups)} 组相似图片。")
            self.results_actions_widget.setVisible(True)

        for i, group in enumerate(self.image_groups):
            group_frame = QFrame(); group_frame.setObjectName("GroupFrame")
            group_layout = QVBoxLayout(group_frame)
            
            best_image_path = get_best_image_in_group(group)

            header_layout = QHBoxLayout()
            title_label = QLabel(f"第 {i+1} 组 (共 {len(group)} 张图片)")
            title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            
            select_group_btn = QPushButton("全选/取消本组")
            
            header_layout.addWidget(title_label); header_layout.addStretch(); header_layout.addWidget(select_group_btn)
            group_layout.addLayout(header_layout)

            group_scroll_area = QScrollArea(); group_scroll_area.setWidgetResizable(True); group_scroll_area.setFixedHeight(280)
            
            images_container = QWidget()
            images_layout = QHBoxLayout(images_container)
            
            group_widgets = []
            for img_path in group:
                img_widget = ImageWidget(img_path, img_path == best_image_path)
                images_layout.addWidget(img_widget)
                self.image_widgets.append(img_widget)
                group_widgets.append(img_widget)
            
            select_group_btn.clicked.connect(lambda _, gw=group_widgets: self.select_group(gw))

            group_scroll_area.setWidget(images_container)
            group_layout.addWidget(group_scroll_area)
            self.results_layout.addWidget(group_frame)

        self.start_btn.setEnabled(True); self.select_folder_btn.setEnabled(True)

    def select_group(self, group_widgets):
        is_any_not_selected = any(not w.is_selected for w in group_widgets)
        for widget in group_widgets:
            widget.set_selected(is_any_not_selected)

    def select_all(self):
        is_any_not_selected = any(not w.is_selected for w in self.image_widgets)
        for widget in self.image_widgets:
            widget.set_selected(is_any_not_selected)

    def auto_select(self):
        for widget in self.image_widgets:
            widget.set_selected(not widget.is_best)

    def delete_selected(self):
        selected_paths = [w.img_path for w in self.image_widgets if w.is_selected]
        if not selected_paths:
            self.status_label.setText("没有选中任何图片。")
            return
        
        deleted_count = 0
        for path in selected_paths:
            try:
                os.remove(path)
                deleted_count += 1
            except OSError as e:
                print(f"Error deleting {path}: {e}")
        
        self.status_label.setText(f"成功删除了 {deleted_count} 张图片，请重新处理以更新视图。")
        self.results_actions_widget.setVisible(False)
        
        for i in reversed(range(self.results_layout.count())): 
            widget_to_remove = self.results_layout.itemAt(i).widget()
            widget_to_remove.setParent(None)
            widget_to_remove.deleteLater()
        self.image_widgets.clear()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    if os.path.exists('icon.ico'):
        app.setWindowIcon(QIcon('icon.ico'))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())