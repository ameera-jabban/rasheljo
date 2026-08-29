"""Gunicorn production config. Run with: gunicorn -c gunicorn.conf.py config.wsgi:application"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = 30
keepalive = 5
max_requests = 1000       # recycle workers periodically to bound memory growth
max_requests_jitter = 100
accesslog = "-"            # stdout — let the platform handle log routing
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
