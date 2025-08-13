import app
from server import app, open_browser


    # 启动Flask服务器，并打印标识信息
print("Starting Flask server on http://127.0.0.1:18200")
open_browser()
app.run(debug=False, port=18200)