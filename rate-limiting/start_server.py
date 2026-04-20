#!/usr/bin/env python3
"""
start_server.py
---------------
Convenient server startup script for the rate limiter demo.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
