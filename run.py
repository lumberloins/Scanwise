#!/usr/bin/env python3
"""
ScanWise WSGI Application Server Entry Point
Powered by Waitress for production-ready cross-platform deployment.
"""
from waitress import serve
from scanwise import create_app
from scanwise.config import Config

app = create_app()

if __name__ == '__main__':
    print(f"Starting ScanWise Diagnostic Server on http://{Config.HOST}:{Config.PORT} ...")
    serve(app, host=Config.HOST, port=Config.PORT)
