import os
from flask import  render_template, request, jsonify
from PIL import Image
import imagehash
from server import app
from interactive import selected_folders, open_folder_dialog, allowed_file
from img import image_to_base64

def calculate_phash(image_path, hash_size=8):
    """计算图像的感知哈希值（使用PIL库）"""
    try:
        # 使用PIL打开图像
        img = Image.open(image_path)
        
        # 转换为灰度图
        img = img.convert('L')
        
        # 计算感知哈希
        hash_value = imagehash.phash(img, hash_size=hash_size)
        
        # 转换为十六进制字符串
        return str(hash_value)
    except Exception as e:
        print(f"Error calculating phash for {image_path}: {str(e)}")
        return None

def calculate_ahash(image_path, hash_size=8):
    """计算图像的平均哈希值（使用PIL库）"""
    try:
        # 使用PIL打开图像
        img = Image.open(image_path)
        
        # 转换为灰度图
        img = img.convert('L')
        
        # 计算平均哈希
        hash_value = imagehash.average_hash(img, hash_size=hash_size)
        
        # 转换为十六进制字符串
        return str(hash_value)
    except Exception as e:
        print(f"Error calculating ahash for {image_path}: {str(e)}")
        return None

def calculate_dhash(image_path, hash_size=8):
    """计算图像的差异哈希值（使用PIL库）"""
    try:
        # 使用PIL打开图像
        img = Image.open(image_path)
        
        # 转换为灰度图
        img = img.convert('L')
        
        # 计算差异哈希
        hash_value = imagehash.dhash(img, hash_size=hash_size)
        
        # 转换为十六进制字符串
        return str(hash_value)
    except Exception as e:
        print(f"Error calculating dhash for {image_path}: {str(e)}")
        return None

def calculate_hamming_distance(hash1, hash2):
    """计算两个哈希值之间的汉明距离"""
    if len(hash1) != len(hash2):
        return float('inf')
    
    distance = 0
    for i in range(len(hash1)):
        if hash1[i] != hash2[i]:
            distance += 1
    return distance

def calculate_similarity(hash1, hash2):
    """计算两个哈希值之间的相似度百分比"""
    if not hash1 or not hash2:
        return 0
    
    max_distance = len(hash1)
    distance = calculate_hamming_distance(hash1, hash2)
    similarity = (1 - distance / max_distance) * 100
    return similarity

def process_images(folder_paths, threshold, hash_size):
    """处理文件夹中的图片，找出相似的图片组"""
    global image_groups
    image_groups = []
    
    if not folder_paths:
        return []
    
    # 收集所有图片文件
    image_paths = []
    for folder_path in folder_paths:
        # 确保路径使用正确的分隔符
        folder_path = os.path.normpath(folder_path)
        print(f"Processing folder: {folder_path}")
        
        for root, _, files in os.walk(folder_path):
            for file in files:
                if allowed_file(file):
                    # 规范化路径
                    full_path = os.path.normpath(os.path.join(root, file))
                    image_paths.append(full_path)
    
    print(f"Found {len(image_paths)} images")
    
    # 计算每张图片的多种哈希值
    phashes = {}
    ahashes = {}
    dhashes = {}
    
    for image_path in image_paths:
        # 规范化路径
        image_path = os.path.normpath(image_path)
        print(f"Processing image: {image_path}")
        
        # 计算多种哈希值
        phash = calculate_phash(image_path, hash_size)
        ahash = calculate_ahash(image_path, hash_size)
        dhash = calculate_dhash(image_path, hash_size)
        
        if phash:
            phashes[image_path] = phash
        if ahash:
            ahashes[image_path] = ahash
        if dhash:
            dhashes[image_path] = dhash
    
    print(f"Calculated phashes for {len(phashes)} images")
    print(f"Calculated ahashes for {len(ahashes)} images")
    print(f"Calculated dhashes for {len(dhashes)} images")
    
    # 找出相似的图片组
    similarity_groups = []
    processed_images = set()
    
    for image_path in image_paths:
        # 规范化路径
        image_path = os.path.normpath(image_path)
        
        if image_path in processed_images:
            continue
            
        # 创建一个新的相似组
        current_group = [image_path]
        processed_images.add(image_path)
        
        # 查找与当前图片相似的其他图片
        for other_path in image_paths:
            # 规范化路径
            other_path = os.path.normpath(other_path)
            
            if other_path in processed_images or other_path == image_path:
                continue
            
            # 计算多种哈希的相似度
            phash_sim = 0
            ahash_sim = 0
            dhash_sim = 0
            
            if image_path in phashes and other_path in phashes:
                phash_sim = calculate_similarity(phashes[image_path], phashes[other_path])
            
            if image_path in ahashes and other_path in ahashes:
                ahash_sim = calculate_similarity(ahashes[image_path], ahashes[other_path])
            
            if image_path in dhashes and other_path in dhashes:
                dhash_sim = calculate_similarity(dhashes[image_path], dhashes[other_path])
            
            # 综合相似度（加权平均）
            combined_sim = (phash_sim * 0.5 + ahash_sim * 0.3 + dhash_sim * 0.2)
            
            print(f"Similarity between {os.path.basename(image_path)} and {os.path.basename(other_path)}: {combined_sim:.2f}%")
            
            if combined_sim >= threshold:
                current_group.append(other_path)
                processed_images.add(other_path)
        
        # 只有当组内有超过一张图片时才添加到结果中
        if len(current_group) > 1:
            similarity_groups.append(current_group)
    
    print(f"Found {len(similarity_groups)} similarity groups")
    
    # 按组内图片数量降序排序
    similarity_groups.sort(key=lambda x: len(x), reverse=True)
    
    # 保存到全局变量
    image_groups = similarity_groups
    
    return similarity_groups


def get_best_image_in_group(group):
    """获取一组图片中最佳的图片（基于文件大小和分辨率）"""
    if not group:
        return None
    
    # 计算每张图片的得分
    image_scores = []
    
    for image_path in group:
        try:
            # 获取文件大小
            file_size = os.path.getsize(image_path)
            
            # 获取图片尺寸
            with Image.open(image_path) as img:
                width, height = img.size
                resolution = width * height
            
            # 计算得分（文件大小和分辨率的加权平均）
            # 这里我们给分辨率更高的权重，因为它通常更能代表图片质量
            score = (file_size * 0.3 + resolution * 0.7)
            
            image_scores.append({
                'path': image_path,
                'score': score,
                'file_size': file_size,
                'resolution': resolution
            })
        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            # 如果处理出错，给它一个很低的分数
            image_scores.append({
                'path': image_path,
                'score': 0,
                'file_size': 0,
                'resolution': 0
            })
    
    # 按得分降序排序
    image_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # 返回得分最高的图片
    return image_scores[0]['path']



@app.route('/')
def index():
    return render_template('index.html', folders=selected_folders)

@app.route('/select_folder', methods=['POST'])
def select_folder_route():
    """打开文件夹选择对话框"""
    open_folder_dialog()
    return jsonify({'success': True, 'folders': selected_folders})

@app.route('/clear_folders', methods=['POST'])
def clear_folders():
    """清空选中的文件夹列表"""
    global selected_folders
    selected_folders = []
    return jsonify({'success': True})

@app.route('/process_images', methods=['POST'])
def process_images_route():
    data = request.get_json()
    threshold = float(data.get('threshold', 80))
    hash_size = int(data.get('hash_size', 8))
    
    if not selected_folders:
        return jsonify({'error': '没有选择文件夹'}), 400
    
    try:
        # 处理图片，找出相似的图片组
        similarity_groups = process_images(selected_folders, threshold, hash_size)
        
        # 准备返回给前端的数据
        result = []
        for group in similarity_groups:
            group_data = []
            
            # 计算组内所有图片之间的平均相似度
            similarities = []
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    try:
                        # 计算多种哈希的相似度
                        phash1 = calculate_phash(group[i], hash_size)
                        phash2 = calculate_phash(group[j], hash_size)
                        ahash1 = calculate_ahash(group[i], hash_size)
                        ahash2 = calculate_ahash(group[j], hash_size)
                        dhash1 = calculate_dhash(group[i], hash_size)
                        dhash2 = calculate_dhash(group[j], hash_size)
                        
                        phash_sim = calculate_similarity(phash1, phash2) if phash1 and phash2 else 0
                        ahash_sim = calculate_similarity(ahash1, ahash2) if ahash1 and ahash2 else 0
                        dhash_sim = calculate_similarity(dhash1, dhash2) if dhash1 and dhash2 else 0
                        
                        # 综合相似度（加权平均）
                        combined_sim = (phash_sim * 0.5 + ahash_sim * 0.3 + dhash_sim * 0.2)
                        similarities.append(combined_sim)
                    except Exception as e:
                        print(f"Error calculating similarity: {str(e)}")
            
            avg_similarity = sum(similarities) / len(similarities) if similarities else 0
            
            # 获取组内最佳图片
            best_image = get_best_image_in_group(group)
            
            # 准备组内图片数据
            for image_path in group:
                # 规范化路径
                image_path = os.path.normpath(image_path)
                
                group_data.append({
                    "path": image_path,
                    "name": os.path.basename(image_path),
                    "base64": image_to_base64(image_path),
                    "size": os.path.getsize(image_path) if os.path.exists(image_path) else 0,
                    "is_best": image_path == best_image
                })
            
            result.append({
                "images": group_data,
                "similarity": round(avg_similarity, 2)
            })
        
        return jsonify({
            "success": True,
            "groups": result
        })
    except Exception as e:
        print(f"Error in process_images: {str(e)}")
        return jsonify({'error': f'处理图片时出错: {str(e)}'}), 500

@app.route('/delete_image', methods=['POST'])
def delete_image():
    """删除指定图片"""
    data = request.json
    image_path = data.get('image_path', '')
    
    if not image_path:
        return jsonify({"success": False, "error": "未提供图片路径"}), 400
    
    # 规范化路径
    image_path = os.path.normpath(image_path)
    
    if not os.path.exists(image_path):
        return jsonify({"success": False, "error": "图片不存在"}), 404
    
    try:
        # 删除文件
        os.remove(image_path)
        
        # 从全局图片组中移除该图片
        for group in image_groups:
            if image_path in group:
                group.remove(image_path)
                # 如果组内只剩一张图片，移除整个组
                if len(group) <= 1:
                    image_groups.remove(group)
                break
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/auto_delete', methods=['POST'])

def auto_delete():
    """自动删除每组中非最佳的图片"""
    data = request.json
    group_indices = data.get('group_indices', [])
    
    if not group_indices:
        return jsonify({"success": False, "error": "未提供组索引"}), 400
    
    try:
        deleted_images = []
        
        # 处理指定的组
        for group_index in group_indices:
            if group_index < 0 or group_index >= len(image_groups):
                continue
                
            group = image_groups[group_index]
            
            # 获取组内最佳图片
            best_image = get_best_image_in_group(group)
            
            # 删除组内除最佳图片外的所有图片
            for image_path in group:
                if image_path != best_image:
                    try:
                        os.remove(image_path)
                        deleted_images.append(image_path)
                    except Exception as e:
                        print(f"Error deleting image {image_path}: {e}")
            
            # 更新组，只保留最佳图片
            image_groups[group_index] = [best_image]
        
        return jsonify({
            "success": True, 
            "deleted_images": deleted_images,
            "message": f"已删除 {len(deleted_images)} 张图片"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
