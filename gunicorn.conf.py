# Gunicorn Configuration for Render
import os

# Server Socket
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"

# Worker Processes
workers = 2  # จำนวน worker (แนะนำ 2-4 สำหรับ Free tier)
worker_class = "sync"  # ใช้ sync worker (รองรับ Threading)
threads = 2  # จำนวน threads ต่อ worker

# Timeouts
timeout = 120  # เพิ่ม timeout เป็น 120 วินาที (แทนค่า default 30 วินาที)
keepalive = 5

# Logging
accesslog = "-"  # Log ไปที่ stdout
errorlog = "-"  # Error log ไปที่ stderr
loglevel = "info"

# Server Mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Process Naming
proc_name = "mood-tracker"

# Server Hooks
def on_starting(server):
    print("🚀 Gunicorn is starting...")

def on_reload(server):
    print("🔄 Gunicorn is reloading...")

def when_ready(server):
    print("✅ Gunicorn is ready. Spawning workers...")

def on_exit(server):
    print("👋 Gunicorn is shutting down...")

# Worker Processes
def pre_fork(server, worker):
    pass

def post_fork(server, worker):
    print(f"👷 Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    print("🔄 Forked child, re-executing...")

def post_worker_init(worker):
    print(f"✅ Worker initialized (pid: {worker.pid})")