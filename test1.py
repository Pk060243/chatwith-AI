from http.server import HTTPServer, BaseHTTPRequestHandler

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b"<h1>Success!</h1><p>EC2 Port 8000 is working perfectly.</p>")

print("Starting test server on port 8000...")
server = HTTPServer(('0.0.0.0', 8000), SimpleHandler)
server.serve_forever()