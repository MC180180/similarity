import os
import base64
import io
import threading
import tkinter as tk
from tkinter import filedialog
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO
from PIL import Image
import imagehash
from werkzeug.utils import secure_filename
import tempfile
import webbrowser
import time
from concurrent.futures import ThreadPoolExecutor
import hashlib
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['THREAD_POOL_SIZE'] = 4  # 线程池大小

# 添加SocketIO支持
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局变量
selected_folders = []
reference_image_path = None
similar_images = []
image_hash_cache = {}  # 图片哈希缓存
executor = ThreadPoolExecutor(max_workers=app.config['THREAD_POOL_SIZE'])  # 线程池

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'webp'}

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_hash(file_path):
    """获取文件的哈希值，用于缓存"""
    h = hashlib.md5()
    try:
        with open(file_path, 'rb') as file:
            while chunk := file.read(8192):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.error(f"Error getting file hash for {file_path}: {e}")
        return None

def image_to_base64(image_path, max_size=300):
    """将图片转换为base64编码，优化内存使用"""
    try:
        # 使用PIL读取图片
        with Image.open(image_path) as img:
            # 调整图片大小以加快加载速度
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            
            # 转换为RGB格式（如果需要）
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 保存为PNG到内存
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            img_data = buffer.getvalue()
            buffer.close()
            
            # 转换为base64
            return base64.b64encode(img_data).decode('utf-8')
    except Exception as e:
        logger.error(f"Error converting image to base64: {e}")
        return ""

def calculate_image_hashes(image_path, hash_size=8):
    """计算图片的多种哈希值"""
    file_hash = get_file_hash(image_path)
    if not file_hash:
        return None
    
    # 检查缓存
    if file_hash in image_hash_cache:
        return image_hash_cache[file_hash]
    
    try:
        with Image.open(image_path) as image:
            phash = str(imagehash.phash(image, hash_size=hash_size))
            ahash = str(imagehash.average_hash(image, hash_size=hash_size))
            dhash = str(imagehash.dhash(image, hash_size=hash_size))
            
            # 存入缓存
            image_hash_cache[file_hash] = {
                'phash': phash,
                'ahash': ahash,
                'dhash': dhash,
                'timestamp': time.time()
            }
            
            return {
                'phash': phash,
                'ahash': ahash,
                'dhash': dhash
            }
    except Exception as e:
        logger.error(f"Error calculating hashes for {image_path}: {e}")
        return None

def calculate_similarity(hashes1, hashes2):
    """计算两个哈希集合的综合相似度"""
    if not hashes1 or not hashes2:
        return 0
    
    # 计算各种哈希的相似度
    phash_sim = calculate_similarity_value(hashes1['phash'], hashes2['phash'])
    ahash_sim = calculate_similarity_value(hashes1['ahash'], hashes2['ahash'])
    dhash_sim = calculate_similarity_value(hashes1['dhash'], hashes2['dhash'])
    
    # 综合相似度（加权平均）
    return (phash_sim * 0.5 + ahash_sim * 0.3 + dhash_sim * 0.2)

def calculate_similarity_value(hash1, hash2):
    """计算两个哈希值之间的相似度"""
    if hash1 is None or hash2 is None or len(hash1) != len(hash2):
        return 0
    
    max_distance = len(hash1)
    distance = sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
    return (1 - distance / max_distance) * 100

def find_similar_images(reference_path, folder_paths, threshold, hash_size, socket_id=None):
    """在文件夹中查找与参考图片相似的图片"""
    global similar_images
    similar_images = []
    
    if not reference_path or not folder_paths:
        return []
    
    # 计算参考图片的哈希值
    ref_hashes = calculate_image_hashes(reference_path, hash_size)
    if not ref_hashes:
        return []
    
    # 收集所有图片文件
    image_paths = []
    for folder_path in folder_paths:
        folder_path = os.path.normpath(folder_path)
        for root, _, files in os.walk(folder_path):
            for file in files:
                if allowed_file(file):
                    full_path = os.path.normpath(os.path.join(root, file))
                    if full_path != reference_path:
                        image_paths.append(full_path)
    
    total_images = len(image_paths)
    if socket_id:
        socketio.emit('progress', {
            'current': 0, 
            'total': total_images, 
            'percent': 0, 
            'status': '开始比较图片相似度...',
            'stage': 'compare'
        }, room=socket_id)
    
    # 使用线程池处理图片
    processed_count = 0
    lock = threading.Lock()
    
    def process_image(image_path):
        nonlocal processed_count
        
        # 计算图片哈希
        img_hashes = calculate_image_hashes(image_path, hash_size)
        if not img_hashes:
            return
        
        # 计算相似度
        similarity = calculate_similarity(ref_hashes, img_hashes)
        
        # 如果相似度超过阈值，添加到结果中
        if similarity >= threshold:
            with lock:
                similar_images.append({
                    "path": image_path,
                    "name": os.path.basename(image_path),
                    "base64": image_to_base64(image_path),
                    "size": os.path.getsize(image_path) if os.path.exists(image_path) else 0,
                    "similarity": similarity
                })
        
        # 更新进度
        with lock:
            nonlocal processed_count
            processed_count += 1
            if socket_id and processed_count % 5 == 0:
                progress = int((processed_count / total_images) * 100)
                socketio.emit('progress', {
                    'current': processed_count, 
                    'total': total_images, 
                    'percent': progress,
                    'status': f'正在比较图片 {os.path.basename(image_path)}...',
                    'stage': 'compare'
                }, room=socket_id)
    
    # 提交所有任务到线程池
    futures = [executor.submit(process_image, path) for path in image_paths]
    
    # 等待所有任务完成
    for future in futures:
        future.result()
    
    # 按相似度降序排序
    similar_images.sort(key=lambda x: x['similarity'], reverse=True)
    
    # 发送完成进度
    if socket_id:
        socketio.emit('progress', {
            'current': total_images, 
            'total': total_images, 
            'percent': 100,
            'status': '处理完成！',
            'stage': 'complete'
        }, room=socket_id)
    
    return similar_images

def clean_cache():
    """定期清理缓存"""
    current_time = time.time()
    expired_keys = [
        key for key, value in image_hash_cache.items()
        if current_time - value['timestamp'] > 3600  # 1小时后过期
    ]
    for key in expired_keys:
        del image_hash_cache[key]

# 定期清理缓存
def start_cache_cleaner():
    while True:
        time.sleep(600)  # 每10分钟清理一次
        clean_cache()

cache_cleaner_thread = threading.Thread(target=start_cache_cleaner, daemon=True)
cache_cleaner_thread.start()

def open_folder_dialog():
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

def select_reference_image():
    """使用Tkinter选择参考图片"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    # 将窗口置顶
    root.attributes('-topmost', True)
    # 强制窗口获取焦点
    root.focus_force()
    # 将窗口提升到最前面
    root.lift()
    file_path = filedialog.askopenfilename(
        title='选择参考图片',
        filetypes=[('Image files', '*.png *.jpg *.jpeg *.bmp *.webp')],
        parent=root  # 指定父窗口
    )
    root.destroy()
    return file_path

@app.route('/')
def index():
    return render_template('index.html', folders=selected_folders)

@app.route('/select_folder', methods=['POST'])
def select_folder_route():
    open_folder_dialog()
    return jsonify({'success': True, 'folders': selected_folders})

@app.route('/select_reference_image', methods=['POST'])
def select_reference_image_route():
    global reference_image_path
    reference_image_path = select_reference_image()
    if reference_image_path:
        return jsonify({
            'success': True, 
            'reference_image': {
                'path': reference_image_path,
                'name': os.path.basename(reference_image_path),
                'base64': image_to_base64(reference_image_path),
                'size': os.path.getsize(reference_image_path) if os.path.exists(reference_image_path) else 0
            }
        })
    return jsonify({'success': False, 'error': '未选择图片'})

@app.route('/process_images', methods=['POST'])
def process_images_route():
    data = request.get_json()
    threshold = float(data.get('threshold', 80))
    hash_size = int(data.get('hash_size', 8))
    socket_id = data.get('socket_id')
    
    if not selected_folders:
        return jsonify({'error': '没有选择文件夹'}), 400
    
    if not reference_image_path:
        return jsonify({'error': '没有选择参考图片'}), 400
    
    # 在新线程中处理图片
    def process_thread():
        try:
            similar_images = find_similar_images(
                reference_image_path, 
                selected_folders, 
                threshold, 
                hash_size, 
                socket_id
            )
            
            socketio.emit('processing_complete', {
                'success': True, 
                'similar_images': similar_images,
                'reference_image': {
                    'path': reference_image_path,
                    'name': os.path.basename(reference_image_path),
                    'base64': image_to_base64(reference_image_path),
                    'size': os.path.getsize(reference_image_path) if os.path.exists(reference_image_path) else 0
                }
            }, room=socket_id)
        except Exception as e:
            logger.error(f"Error in process_images: {str(e)}")
            socketio.emit('processing_complete', {'success': False, 'error': str(e)}, room=socket_id)
    
    thread = threading.Thread(target=process_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': '处理已开始'})

@app.route('/delete_image', methods=['POST'])
def delete_image():
    global similar_images
    
    data = request.json
    image_path = data.get('image_path', '')
    
    logger.debug(f"Delete request received for image: {image_path}")
    
    if not image_path:
        logger.error("No image path provided in delete request")
        return jsonify({"success": False, "error": "未提供图片路径"}), 400
    
    # 确保路径格式正确
    image_path = os.path.normpath(image_path)
    logger.debug(f"Normalized image path: {image_path}")
    
    # 检查文件是否存在
    if not os.path.exists(image_path):
        logger.error(f"Image does not exist: {image_path}")
        return jsonify({"success": False, "error": "图片不存在"}), 404
    
    try:
        # 删除文件
        os.remove(image_path)
        logger.info(f"Successfully deleted image: {image_path}")
        
        # 从相似图片列表中移除该图片
        similar_images = [img for img in similar_images if img['path'] != image_path]
        logger.debug(f"Removed image from similar_images list. Remaining: {len(similar_images)}")
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting image {image_path}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/delete_all_similar', methods=['POST'])
def delete_all_similar():
    global similar_images
    
    data = request.json
    socket_id = data.get('socket_id')
    
    logger.debug("Delete all similar images request received")
    
    if not similar_images:
        logger.error("No similar images found for deletion")
        return jsonify({"success": False, "error": "没有找到相似图片"}), 400
    
    try:
        deleted_images = []
        failed_images = []
        
        for img in similar_images:
            image_path = img['path']
            logger.debug(f"Attempting to delete image: {image_path}")
            
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
                    deleted_images.append(image_path)
                    logger.info(f"Successfully deleted image: {image_path}")
                else:
                    logger.warning(f"Image does not exist, skipping: {image_path}")
                    failed_images.append(image_path)
            except Exception as e:
                logger.error(f"Error deleting image {image_path}: {e}")
                failed_images.append(image_path)
        
        # 清空相似图片列表
        similar_images = []
        
        socketio.emit('delete_complete', {
            'success': True,
            'deleted_count': len(deleted_images),
            'failed_count': len(failed_images),
            'message': f'已删除 {len(deleted_images)} 张相似图片'
        }, room=socket_id)
        
        logger.info(f"Delete all operation completed. Deleted: {len(deleted_images)}, Failed: {len(failed_images)}")
        
        return jsonify({
            "success": True,
            "deleted_count": len(deleted_images),
            "failed_count": len(failed_images),
            "message": f'已删除 {len(deleted_images)} 张相似图片'
        })
    except Exception as e:
        logger.error(f"Error in delete_all_similar: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

def open_browser():
    def _open_browser():
        time.sleep(1.5)
        webbrowser.open('http://127.0.0.1:18210')
    
    thread = threading.Thread(target=_open_browser)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    logger.info("Starting Flask server on http://127.0.0.1:18210")
    open_browser()
    socketio.run(app, debug=False, port=18210)
