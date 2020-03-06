import os
import urllib.parse
import gzip
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

class API():
    def do_get(self, data):
        pass

    def do_post(self, data):
        pass

    def log_message(self, address, timestamp, data):
        pass

    def set_fn_do_get(self, fn):
        self.do_get = fn

    def set_fn_do_post(self, fn):
        self.do_post = fn

    def set_fn_log_message(self, fn):
        self.log_message = fn

class RequestHandler(SimpleHTTPRequestHandler):
    """This handler uses server.base_path instead of always using os.getcwd()"""
    def translate_path(self, path):
        path = SimpleHTTPRequestHandler.translate_path(self, path)
        relpath = os.path.relpath(path, os.getcwd())
        fullpath = os.path.join(self.server.base_path, relpath)
        return fullpath

    def set_headers(self, type="text/plain"):
        self.send_response(200)
        self.send_header('Content-Type', type)
        self.end_headers()

    def do_GET(self):
        response = self.server.do_get(self)
        if response:
            self.set_headers()
            self.wfile.write(response.encode())
        else:
            """ support for gzip compression """
            path = self.translate_path(self.path)
            if path.endswith(('css', 'js', 'woff2', 'woff', 'ttf')):
                with open(path, 'rb') as content:
                    self.send_response(200)
                    ctype = self.guess_type(path)
                    self.send_header('Content-Type', ctype)
                    self.send_header('Content-Encoding', "gzip")
                    fs = os.fstat(content.fileno())
                    content_length = fs[6]
                    content = content.read()
                    if len(content) > 100:
                        if 'accept-encoding' in self.headers:
                            if 'gzip' in self.headers['accept-encoding']:
                                content = gzip.compress(content)
                                content_length = len(content)
                    self.send_header('Content-Length', content_length)
                    self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
                    self.end_headers()
                    self.wfile.write(content)
                    self.wfile.flush()
            else:
                SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        self.server.do_post(self)

    def log_message(self, format, *args):
        self.server.log_message(self.address_string(), self.log_date_time_string(), format%args)

class HTTPWebserver(ThreadingMixIn, HTTPServer, API):
    """The main server, you pass in path which is the path you want to serve requests from"""
    allow_reuse_address = True
    daemon_threads = True  # comment to keep threads alive until finished

    def __init__(self, port, path, RequestHandler=RequestHandler):
        self.port = port
        self.base_path = path
        HTTPServer.__init__(self, ('', self.port), RequestHandler)

if __name__ == '__main__':
    def poster(data):
        for key in list(data.keys()):
            if key == 'cmd':
                if data[key][0] == 'ip':
                    return (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [[(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]
        return None

    def logger(address, timestamp, data):
        print("[%s] : %s %s\n" % (timestamp, address, data))

    import socket
    port = 8080
    path = 'web'
    base_path = os.path.join(os.path.dirname(__file__), path)
    httpd = Webserver(port, base_path)
    try:
        print("server running")
        httpd.set_fn_do_post(poster)
        httpd.set_fn_log_message(logger)
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
