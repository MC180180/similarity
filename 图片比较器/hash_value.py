from PIL import Image
import imagehash

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