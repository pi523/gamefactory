"""本地预览服务（no-store：改完代码刷新即生效，不用清缓存）。用法: python3 factory/serve.py [端口=8765]，然后开 http://127.0.0.1:8765/preview.html"""
import http.server, socketserver, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate'); self.send_header('Pragma', 'no-cache'); self.send_header('Expires', '0'); super().end_headers()
    def log_message(self, *a): pass
if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', port), lambda *a, **k: H(*a, directory=str(ROOT), **k)) as s:
        print(f'http://127.0.0.1:{port}/preview.html'); s.serve_forever()
