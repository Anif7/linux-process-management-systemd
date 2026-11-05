import os
import signal
import sys
import time

# 1. Configuration via Environment Variables
SERVICE_NAME = os.getenv("SERVICE_NAME", "testpress-worker")
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "5"))
CRASH_AFTER = int(os.getenv("CRASH_AFTER", "0"))  # 0 = disabled; >0 = crashes after N heartbeats
CRASH_FILE = os.getenv("CRASH_FILE", "/tmp/crash_worker")  # Trigger crash if this file exists

# 2. Signal Handling (Graceful Shutdown)
def handle_shutdown(signum, frame):
    signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
    print(f"\n[{SERVICE_NAME}] Received signal {signum} ({signal_name}). Performing graceful shutdown...", flush=True)
    time.sleep(1)  # Simulate completing in-flight work
    print(f"[{SERVICE_NAME}] Cleanup completed. Exiting cleanly.", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

# 3. Startup Information
print(f"[{SERVICE_NAME}] Started with PID: {os.getpid()}", flush=True)
print(f"[{SERVICE_NAME}] Configuration: INTERVAL={HEARTBEAT_INTERVAL}s, CRASH_AFTER={CRASH_AFTER}", flush=True)

# 4. Main Service Loop
heartbeat_count = 0
try:
    while True:
        heartbeat_count += 1
        print(f"[{SERVICE_NAME}] Heartbeat #{heartbeat_count}: worker is alive (PID: {os.getpid()})", flush=True)

        # Crash condition 1: After a specified number of heartbeats
        if CRASH_AFTER > 0 and heartbeat_count >= CRASH_AFTER:
            print(f"[{SERVICE_NAME}] CRASH TRIGGER: Reached {heartbeat_count} heartbeats (CRASH_AFTER={CRASH_AFTER})!", flush=True)
            raise RuntimeError("Fatal worker error: CRASH_AFTER limit reached.")

        # Crash condition 2: If a trigger file is detected (e.g., touch /tmp/crash_worker)
        if os.path.exists(CRASH_FILE):
            print(f"[{SERVICE_NAME}] CRASH TRIGGER: Found crash file {CRASH_FILE}!", flush=True)
            raise RuntimeError(f"Fatal worker error: Trigger file {CRASH_FILE} exists.")

        # Resource limit test: simulate memory allocation exceeding cgroup limit
        if os.path.exists("/tmp/leak_memory"):
            print(f"[{SERVICE_NAME}] ALLOCATING MEMORY: Attempting to allocate 100 MB...", flush=True)
            leak_data = bytearray(100 * 1024 * 1024)

        time.sleep(HEARTBEAT_INTERVAL)

except Exception as e:
    print(f"[{SERVICE_NAME}] Process crashed with error: {e}", flush=True)
    sys.exit(1)  # Exit code 1 indicates abnormal termination to systemd