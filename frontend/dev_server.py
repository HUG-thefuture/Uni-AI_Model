"""前端开发服务器:在 http.server 基础上禁用缓存,保证 HTML/JS/CSS 改动即时生效。

用法(仓库根目录):
  python frontend/dev_server.py 4174
之前用 `python -m http.server` 时浏览器会按启发式缓存旧页面,导致前端修复"不生效";
本服务器给所有响应加 Cache-Control: no-cache,开发期请统一使用。
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[frontend] %s\n" % (fmt % args))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4174
    directory = None
    # 默认以本文件所在目录(frontend/)为根
    handler = partial(NoCacheHandler, directory=directory)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"前端开发服务已启动: http://127.0.0.1:{port} (缓存已禁用)")
    server.serve_forever()


if __name__ == "__main__":
    main()
