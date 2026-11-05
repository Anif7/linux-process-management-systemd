# Linux Process Management & systemd

Hands-on engineering lab on Linux process supervision, signal handling, resource management via cgroups, and service lifecycle management using `systemd`.

---

## Table of Contents
1. [Overview](#overview)
2. [Deliverables & Repository Structure](#deliverables--repository-structure)
3. [Key Design Decisions](#key-design-decisions)
4. [Installation & Setup](#installation--setup)
5. [Configuration](#configuration)
6. [Managing the Service](#managing-the-service)
7. [Step-by-Step Reproduction Guide](#step-by-step-reproduction-guide)
8. [Troubleshooting & Exit Status Reference](#troubleshooting--exit-status-reference)
9. [Demonstration Questions & Answers](#demonstration-questions--answers)

---

## Overview

At Testpress, background services such as Celery workers, cron jobs, and Django application servers must run reliably 24/7. This project demonstrates how Linux manages background processes natively and how `systemd` acts as an init system and process supervisor to provide:
* Automatic recovery from unexpected crashes.
* Clean graceful shutdown handling on termination requests.
* Strict CPU and Memory isolation via Linux Control Groups (cgroups).
* Centralized, structured logging through `journald`.
* Automatic persistence across system reboots.

---

## Deliverables & Repository Structure

```text
.
├── app.py                      # Python background worker with signal & crash simulation
├── testpress-worker.service    # systemd unit definition file
├── testpress-worker.env        # Environment configuration file
├── experiments.md              # Detailed records, observations, and technical explanations
├── README.md                   # Setup, reproduction instructions, and demonstration notes
└── evidence/                   # Screenshots proving personal execution and testing
    ├── 01_running_process.png
    ├── 02_graceful_shutdown.png
    ├── 03_forced_termination.png
    ├── 04_systemd_service.png
    ├── 05_automatic_restart.png
    ├── 06_crash_investigation.png
    ├── 07_invalid_configuration.png
    ├── 08_repeated_crashes.png
    ├── 09_resource_limits.png
    └── 10_reboot_persistence.png
```

> **Note:** For the complete log of actions, expectations, observations, and deep explanations across all 10 experiments, see [experiments.md](experiments.md).

---

## Key Design Decisions

1. **Zero External Dependencies:** Built using Python's standard library (`os`, `signal`, `sys`, `time`) to keep the footprint lightweight.
2. **Signal Trapping:** Uses Python's `signal.signal()` for `SIGTERM` and `SIGINT` to allow graceful resource cleanup before termination.
3. **Least Privilege Principle:** Runs under an unprivileged dedicated system user (`testpress`) with no login shell (`/usr/sbin/nologin`).
4. **Environment Separation:** Configuration parameters are decoupled into `testpress-worker.env` via systemd's `EnvironmentFile` directive.
5. **Cgroup Resource Sandboxing:** Bound to `MemoryMax=50M` and `CPUQuota=50%` to protect the host OS from runaway memory leaks or CPU starvation.

---

## Installation & Setup

### Prerequisites
* Linux environment (Ubuntu 22.04 LTS or compatible systemd-based Linux distribution).
* Python 3 installed at `/usr/bin/python3`.
* `sudo` administrative privileges.

### Step 1: Navigate to the Project Directory
Clone or enter the project repository directory:
```bash
cd linux-process-management-systemd
```

### Step 2: Create the Dedicated System User
```bash
sudo useradd -r -s /usr/sbin/nologin testpress
```

### Step 3: Configure Directory Traversal Permissions
By default on Ubuntu, user home directories have private permissions (`750`). Grant traversal (`+x`) permission on `$HOME` so that the unprivileged `testpress` user can traverse into your project directory:
```bash
chmod o+x $HOME
```

### Step 4: Update Paths & Install the Service File

Because systemd requires **full absolute paths**, make sure `testpress-worker.service` points to where this project is located on your machine:

1. Check your current directory path by running:
   ```bash
   pwd
   ```

2. Open `testpress-worker.service` and ensure these three lines match your `pwd` path:
   ```ini
   WorkingDirectory=/path/to/linux-process-management-systemd
   EnvironmentFile=/path/to/linux-process-management-systemd/testpress-worker.env
   ExecStart=/usr/bin/python3 -u /path/to/linux-process-management-systemd/app.py
   ```
   *(Shortcut: You can also run this command to fill your current path automatically without editing manually:)*
   ```bash
   PROJECT_DIR=$(pwd)
   sed -i "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" testpress-worker.service
   sed -i "s|EnvironmentFile=.*|EnvironmentFile=$PROJECT_DIR/testpress-worker.env|" testpress-worker.service
   sed -i "s|ExecStart=/usr/bin/python3 -u .*|ExecStart=/usr/bin/python3 -u $PROJECT_DIR/app.py|" testpress-worker.service
   ```

3. Copy the service unit file to systemd's configuration directory:
   ```bash
   sudo cp testpress-worker.service /etc/systemd/system/testpress-worker.service
   ```

### Step 5: Reload Daemon, Enable and Start the Service
```bash
# Tell systemd to re-scan unit files
sudo systemctl daemon-reload

# Enable automatic startup on system boot
sudo systemctl enable testpress-worker

# Start the service immediately
sudo systemctl start testpress-worker
```

### Step 6: Verify Service Status
```bash
systemctl status testpress-worker
```

---

## Configuration

Configuration values are loaded through `testpress-worker.env`:

| Variable | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `testpress-worker` | Identifier prefixed to all log entries. |
| `HEARTBEAT_INTERVAL` | `5` | Number of seconds between heartbeat log emissions. |
| `CRASH_AFTER` | `0` | If set to `N > 0`, crashes automatically after `N` heartbeats. |
| `CRASH_FILE` | `/tmp/crash_worker` | If this file exists on disk, triggers an immediate crash. |

---

## Managing the Service

| Task | Command |
|---|---|
| Check status & recent logs | `systemctl status testpress-worker` |
| Start service | `sudo systemctl start testpress-worker` |
| Stop service gracefully | `sudo systemctl stop testpress-worker` |
| Restart service | `sudo systemctl restart testpress-worker` |
| Enable on boot | `sudo systemctl enable testpress-worker` |
| Disable on boot | `sudo systemctl disable testpress-worker` |
| Follow live logs | `journalctl -u testpress-worker -f` |
| View last 50 log lines | `journalctl -u testpress-worker -n 50 --no-pager` |
| Inspect cgroup limits | `systemctl show testpress-worker -p MemoryMax -p CPUQuotaPerSecUSec` |
| Clear failed state / rate limit | `sudo systemctl reset-failed testpress-worker` |

---

## Step-by-Step Reproduction Guide

> For the comprehensive experiment write-up with technical explanations and mapped evidence screenshots, refer to [experiments.md](experiments.md).

To independently reproduce the 10 experiments and verify behavior:

### Experiment 1: Running Process Inspection
1. Run manually: `python3 app.py &`
2. Inspect with: `ps aux | grep app.py`, `pgrep -la python3`, `pidof python3`, and `pstree -p -s <PID>`.
3. Check priority: `ps -o pid,comm,nice -p <PID>` and adjust: `renice -n 10 -p <PID>`.

### Experiment 2: Graceful Termination with SIGTERM
1. While `app.py` is running, send `kill -15 <PID>`.
2. Observe graceful shutdown log: `Received signal 15 (SIGTERM)... Cleanup completed. Exiting cleanly.`

### Experiment 3: Forced Termination with SIGKILL
1. While `app.py` is running, send `kill -9 <PID>`.
2. Observe immediate termination with `Killed` and zero shutdown logs.

### Experiment 4: Managing under systemd
1. Start via systemd: `sudo systemctl start testpress-worker`.
2. Run `systemctl status testpress-worker` to verify `active (running)`.

### Experiment 5: Automatic Restart after SIGKILL
1. Note the PID from `systemctl status testpress-worker`.
2. Kill the worker with `sudo kill -9 <PID>`.
3. Wait 6 seconds, run `systemctl status testpress-worker`, and observe the new PID.

### Experiment 6: Crash Investigation via journalctl
1. Trigger a crash: `touch /tmp/crash_worker && rm -f /tmp/crash_worker`.
2. Inspect logs: `journalctl -u testpress-worker -n 25 --no-pager`.
3. Observe the crash traceback and systemd's scheduled restart job.

### Experiment 7: Invalid Executable Path
1. Edit unit: `sudo sed -i 's|python3|python3_invalid|' /etc/systemd/system/testpress-worker.service`.
2. Reload & restart: `sudo systemctl daemon-reload && sudo systemctl restart testpress-worker`.
3. Check status: `systemctl status testpress-worker` shows `status=203/EXEC`.
4. Restore valid binary path afterwards.

### Experiment 8: Repeated Crashes & Rate Limiting
1. In `testpress-worker.env`, set `CRASH_AFTER=1` and `HEARTBEAT_INTERVAL=1`.
2. In unit file, set `RestartSec=1s`, `StartLimitIntervalSec=20s`, `StartLimitBurst=5`.
3. Reload & restart. After 5 quick failures, systemd trips the circuit breaker: `Start request repeated too quickly.`
4. Restore parameters and reset: `sudo systemctl reset-failed testpress-worker`.

### Experiment 9: Memory Limits & OOM Killer
1. Ensure unit contains `MemoryMax=50M` and `CPUQuota=50%`.
2. Trigger allocation exceeding 50 MB: `touch /tmp/leak_memory && rm -f /tmp/leak_memory`.
3. Check journald: `journalctl -u testpress-worker -n 25 --no-pager`.
4. Observe: `A process of this unit has been killed by the OOM killer.` followed by automatic restart.

### Experiment 10: Reboot Persistence
1. Verify unit is enabled: `systemctl is-enabled testpress-worker`.
2. Reboot the system (`wsl --shutdown` on Windows, or `sudo reboot`).
3. Reopen terminal and check: `uptime -s && uptime -p` followed by `systemctl status testpress-worker`.
4. Observe the service started automatically without manual invocation.

---

## Troubleshooting & Exit Status Reference

| Status Code | Meaning | Cause in this Lab | Resolution |
|---|---|---|---|
| **`status=200/CHDIR`** | Failed to change directory | Non-root user `testpress` could not traverse parent directories to reach `WorkingDirectory`. | Run `chmod o+x /home/<user>` to allow directory traversal. |
| **`status=203/EXEC`** | Failed to execute binary | The path defined in `ExecStart` does not exist on disk or lacks execute permissions. | Correct the binary path (e.g. `/usr/bin/python3`) and ensure it is absolute. |
| **`status=9/KILL` / `result=oom-kill`** | Out of Memory Kill | Process RAM exceeded the cgroup `MemoryMax=50M` threshold. | Increase `MemoryMax` or optimize memory usage inside the worker. |
| **`Start request repeated too quickly`** | Restart Rate Limit tripped | Service failed more than `StartLimitBurst` times within `StartLimitIntervalSec`. | Fix the underlying application crash and reset status via `sudo systemctl reset-failed <unit>`. |

---

## Demonstration Questions & Answers

### 1. What is the difference between SIGTERM and SIGKILL?
* **`SIGTERM` (signal 15)** is a polite termination request. The process can intercept it, invoke signal handlers, complete in-progress work, flush file buffers, and exit cleanly with code `0`.
* **`SIGKILL` (signal 9)** is an uncatchable forced termination executed directly by the Linux kernel. The process has no opportunity to run cleanup code, increasing the risk of data corruption or unfinished state.

### 2. Why doesn't `nohup` provide the same reliability as systemd?
* `nohup` only prevents a process from receiving `SIGHUP` when its controlling terminal session closes.
* It does **not** provide process monitoring: if the process crashes, `nohup` will not restart it.
* It does **not** persist across server reboots.
* It lacks resource isolation (cgroups), start rate limiting, structured logging (`journald`), and dependency management.

### 3. What happens when a service crashes repeatedly?
Systemd triggers **Start Rate Limiting**. If a service restarts more than `StartLimitBurst` times (default 5) within `StartLimitIntervalSec` (e.g. 10s or 100s), systemd trips its circuit breaker, transitions the unit to `failed`, logs `Start request repeated too quickly`, and stops attempting restarts until an administrator runs `systemctl reset-failed`.

### 4. What is the difference between restarting a process and restarting a service?
* **Restarting a process** simply kills a specific PID and spawns a new PID without reloading environment files or re-evaluating system dependencies.
* **Restarting a service (`systemctl restart`)** invokes systemd's orchestration: it stops the old cgroup, re-reads environment files, reapplies resource quotas, resets counters, and starts the unit afresh through its configured lifecycle.

### 5. What happens to child processes when a systemd service is stopped?
Because systemd places each service into its own dedicated **Control Group (cgroup)**, stopping a service causes systemd to terminate **all processes inside that cgroup** (using `KillMode=control-group` by default). This guarantees that rogue child processes, background workers, or orphaned threads cannot escape and remain running as orphans.

### 6. How would you ensure a Celery worker finishes its current task before shutting down?
1. **Send SIGTERM:** Celery workers catch `SIGTERM` (or `SIGQUIT`) to initiate "warm shutdown", finishing current active tasks while refusing to pick up new ones from the broker.
2. **Configure `TimeoutStopSec` in systemd:** In the service unit, set `TimeoutStopSec=300s` (or appropriate duration) to give the worker sufficient time to complete long-running jobs before systemd resorts to `SIGKILL`.

