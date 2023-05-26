# -*- coding: utf-8 -*-
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            "login": "781462248",
            "password": "674597435",
            "provider": "Archive - Player v.4",
            "IPTVServer": "http:\/\/core.nasche.tv\/iptv\/api\/v1",
            "autostart": "1",
            "boxconfig_version": "1234",
            "video-player": "4097",
            "movie-player": "4097",
            "menulanguage": "2"
        }
        json_response = json.dumps(response)
        self.wfile.write(json_response.encode('utf-8'))

def run(server_class=HTTPServer, handler_class=SimpleHTTPRequestHandler, port=8889):
    server_address = ('0.0.0.0', port)
    httpd = server_class(server_address, handler_class)
    print('Starting httpd...')
    httpd.serve_forever()

if __name__ == "__main__":
    run()
