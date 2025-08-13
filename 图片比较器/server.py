import tempfile
import shutil
from flask import Flask, jsonify
import time
import threading
import webbrowser



app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

@app.route('/cleanup', methods=['POST'])
def cleanup():
    try:
        shutil.rmtree(app.config['UPLOAD_FOLDER'])
        app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        return jsonify({'success': True, 'message': '临时文件已清理'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def open_browser():
    """延迟打开浏览器"""
    def _open_browser():
        time.sleep(1.5)  # 等待Flask服务器启动
        webbrowser.open('http://127.0.0.1:18200')
    
    thread = threading.Thread(target=_open_browser)
    thread.daemon = True
    thread.start()
