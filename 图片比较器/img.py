import base64
import io
from PIL import Image

def image_to_base64(image_path):
    """将图片转换为base64编码"""
    try:
        # 使用PIL读取图片
        img = Image.open(image_path)
        
        # 调整图片大小以加快加载速度
        max_size = 300
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # 转换为RGB格式（如果需要）
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 保存为PNG到内存
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_data = buffer.getvalue()
        
        # 转换为base64
        return base64.b64encode(img_data).decode('utf-8')
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        return ""