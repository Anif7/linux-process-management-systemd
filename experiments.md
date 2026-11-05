# Linux Process Management & systemd Experiments

This document records hands-on experiments, observations, and technical explanations conducted during the engineering lab exercise.

---

## Experiment 1: Running Process Inspection

### 1. Action
* Started the Python worker: `python3 app.py`
* Inspected running processes from a second terminal using:
  * `ps aux | grep app.py`
  * `pgrep -la python3`
  * `pidof python3`
  * `pstree -p -s <PID>`
  * `top -p <PID>`
  * Job control (`Ctrl+Z`, `jobs`, `bg %1`, `fg %1`)
  * Process priority inspection and adjustment: `renice -n 10 -p <PID>`

### 2. Expectation
* The Python script should appear in the process table with a unique PID.
* `ps` and `top` should show low CPU and memory footprint since the process sleeps between heartbeats.
* `pstree` should trace the process back through the shell to `systemd` (PID 1).

### 3. Observation
* The process ran with PID `598371` under user `anif`.
* State was `S+` (Interruptible Sleep, foreground process group).
* Memory usage (`RSS` / `RES`) was ~9000 KB (~9 MB), CPU was `0.0%`.
* `pstree` confirmed the hierarchy: `systemd(1) -> ... -> bash(552960) -> python3(598371)`.
* Suspending with `Ctrl+Z` paused output and changed state to `T` (`Stopped` in `jobs`). Resuming with `bg` returned the shell prompt while heartbeats continued.
* `renice -n 10` successfully adjusted the nice value from `0` to `10`.

### 4. Explanation
* **The Process Family Tree:** Every single program in Linux traces its origins back to `systemd` (PID 1). Our Python script was launched from our interactive `bash` shell, making `bash` its parent process.
* **Why CPU was 0.0%:** Because the script sleeps for 5 seconds between heartbeats, it sits idle in "interruptible sleep" (`S`), freeing up the CPU completely for other programs.
* **Pausing and Resuming (`Ctrl+Z` / `bg`):** Pressing `Ctrl+Z` freezes the process in place without terminating it (`Stopped` state). Typing `bg` tells the process to wake back up and run in the background, giving us our terminal prompt back.
* **Niceness:** Niceness controls how polite a program is about sharing CPU time. A higher nice value (+10) tells the Linux scheduler: *"I am very nice—feel free to give CPU time to other programs before me."*

**Evidence:** [evidence/01_running_process.png](evidence/01_running_process.png)

---

## Experiment 2: Graceful Shutdown with SIGTERM

### 1. Action
* Executed `kill -15 632001` (or `pkill -15 -f app.py`) while `python3 app.py` was running.

### 2. Expectation
* The process should intercept `SIGTERM`, invoke its signal handler, perform cleanup, log its graceful termination, and exit with status code 0.

### 3. Observation
* The application intercepted signal 15 and printed:
  ```text
  Received signal 15 (SIGTERM). Performing graceful shutdown...
  Cleanup completed. Exiting cleanly.
  ```
* The process exited cleanly back to the terminal prompt.

### 4. Explanation
* **A Polite Request to Stop:** `SIGTERM` (signal 15) is Linux's standard way of telling a program: *"Please finish up your work and shut down."*
* **Intercepting the Signal:** Because Python allows us to catch `SIGTERM` using `signal.signal()`, our script can finish writing data, close open database connections, print a shutdown log, and exit cleanly with code `0`.

**Evidence:** [evidence/02_graceful_shutdown.png](evidence/02_graceful_shutdown.png)

---

## Experiment 3: Forced Termination with SIGKILL

### 1. Action
* Executed `kill -9 636754` while `python3 app.py` was running.
* Verified termination with `ps -p 636754`.

### 2. Expectation
* The process should terminate immediately without executing the Python cleanup handler or logging any shutdown message.

### 3. Observation
* The terminal immediately printed `Killed` and returned to the shell prompt.
* No graceful shutdown or cleanup messages were printed.
* `ps -p 636754` confirmed the process was completely gone from the process table.

### 4. Explanation
* **No Negotiation (Forced Kill):** `SIGKILL` (signal 9) is an immediate termination order handled directly by the Linux kernel. The program never gets a chance to see the signal or execute any cleanup code.
* **The Tradeoff:** While `kill -9` is guaranteed to stop a frozen or runaway program, it risks leaving files half-written or database state corrupted because the application is wiped from memory instantly.

**Evidence:** [evidence/03_forced_termination.png](evidence/03_forced_termination.png)

---

## Experiment 4: Managing the Service with systemd & Permission Troubleshooting

### 1. Action
* Created dedicated system user `testpress`: `sudo useradd -r -s /usr/sbin/nologin testpress`.
* Configured environment file `testpress-worker.env` and service unit `testpress-worker.service`.
* Installed unit file to `/etc/systemd/system/testpress-worker.service`, reloaded systemd (`sudo systemctl daemon-reload`), enabled boot startup (`sudo systemctl enable testpress-worker`), and started service (`sudo systemctl start testpress-worker`).
* Diagnosed failure and applied permission traversal fix: `chmod o+x /home/anif`.
* Restarted service and checked status: `systemctl status testpress-worker`.

### 2. Expectation
* The service should start under non-root user `testpress`, load environment variables, write heartbeats to journald, and report `active (running)`.

### 3. Observation
* Initial start failed with `code=exited, status=200/CHDIR` and log: `Changing to the requested working directory failed: Permission denied`.
* After running `chmod o+x /home/anif`, the service successfully transitioned to `active (running)` with PID `678705`.
* `systemctl status` confirmed:
  * Unit is `enabled` (starts on boot).
  * Placed inside cgroup `/system.slice/testpress-worker.service`.
  * Logs with timestamps and heartbeats forwarded to `systemd-journald`.

### 4. Explanation
* **Why `200/CHDIR` happened:** Systemd drops root privileges to our service user `testpress` before starting the script. In Ubuntu, user home directories (`/home/anif`) have private permissions (`750`), meaning outside users cannot even pass through them. Because `testpress` was blocked from entering the folder, systemd failed with `status=200/CHDIR` (*Permission denied*).
* **The Fix:** Running `chmod o+x /home/anif` gave `testpress` permission to walk through the folder path into the project workspace.
* **Centralized Logging:** Systemd automatically forwards the worker's stdout/stderr to `journald`, so all heartbeats and errors are timestamped and preserved without needing manual log files.

**Evidence:** [evidence/04_systemd_service.png](evidence/04_systemd_service.png)

---

## Experiment 5: Automatic Restart after Unexpected Termination (SIGKILL)

### 1. Action
* Started the service under systemd and recorded the initial PID: `686526`.
* Forcibly terminated the worker process: `sudo kill -9 686526`.
* Monitored the service status after the restart delay: `systemctl status testpress-worker`.

### 2. Expectation
* Because `Restart=on-failure` is configured and `SIGKILL` represents an uncaught fatal signal, systemd should detect the abnormal crash, wait `RestartSec=5s`, and automatically respawn the worker with a new PID.

### 3. Observation
* The worker process `686526` was immediately terminated by the kernel.
* Systemd detected `status=9/KILL`, scheduled a restart, and after 5 seconds automatically started a new worker process with PID `686767`.
* Heartbeats resumed automatically without manual intervention.

### 4. Explanation
* **The Service Watchdog:** Systemd constantly monitors the PID of our running worker.
* **Distinguishing Accidents from Intent:** When we killed the worker with `kill -9`, the process died unexpectedly (`status=9/KILL`). Systemd knew this was an abnormal crash, not an intentional shutdown.
* **Automated Recovery:** Thanks to `Restart=on-failure`, systemd waited 5 seconds and automatically spawned a brand new worker with a new PID, keeping our background service alive without any human intervention.

**Evidence:** [evidence/05_automatic_restart.png](evidence/05_automatic_restart.png)

---

## Experiment 6: Crash Investigation using journalctl & Exit Code Handling

### 1. Action
* Triggered an internal simulated application crash: `touch /tmp/crash_worker`.
* Cleared the trigger file: `rm -f /tmp/crash_worker`.
* Investigated the crash timeline using: `journalctl -u testpress-worker -n 25 --no-pager`.

### 2. Expectation
* The Python application should detect the trigger file, raise an unhandled `RuntimeError`, log the error, and exit with status code 1.
* Systemd should capture the error log, recognize the failure (`status=1/FAILURE`), and schedule an automatic restart.

### 3. Observation
* `journalctl` captured the full diagnostic trace:
  * `CRASH TRIGGER: Found crash file /tmp/crash_worker!`
  * `Process crashed with error: Fatal worker error: Trigger file /tmp/crash_worker exists.`
  * `Main process exited, code=exited, status=1/FAILURE`
  * `Scheduled restart job, restart counter is at 2.`
  * `Started Testpress Background Worker Service` with new PID `689637`.

### 4. Explanation
* **Exit Codes as Status Reports:** When a Linux program finishes, it returns an exit code: `0` means *"everything succeeded"*, while any number from `1` to `255` means *"something broke"*.
* **Detecting Crashes:** When our Python script raised an unhandled error and ran `sys.exit(1)`, systemd saw exit code `1` and treated it as a failure (`status=1/FAILURE`), triggering a restart.
* **Diagnosing via `journalctl`:** Because systemd captures and timestamps all output, running `journalctl -u testpress-worker` let us see the exact error message and the recovery timeline in plain English.

**Evidence:** [evidence/06_crash_investigation.png](evidence/06_crash_investigation.png)

---

## Experiment 7: Invalid Configuration Handling (status=203/EXEC)

### 1. Action
* Modified `ExecStart` in `/etc/systemd/system/testpress-worker.service` to point to a non-existent binary: `ExecStart=/usr/bin/python3_invalid ...`.
* Reloaded configuration (`sudo systemctl daemon-reload`) and restarted the service (`sudo systemctl restart testpress-worker`).
* Inspected service state: `systemctl status testpress-worker`.

### 2. Expectation
* Systemd should fail during process invocation and flag the service with an execution failure.

### 3. Observation
* `systemctl status` reported `code=exited, status=203/EXEC` and `Active: activating (auto-restart) (Result: exit-code)`.
* Systemd logged: `Failed at step EXEC spawning /usr/bin/python3_invalid: No such file or directory`.

### 4. Explanation
* **The Missing Program:** When systemd tried to launch our service, it looked for `/usr/bin/python3_invalid` on disk and discovered it does not exist.
* **Decoding `203/EXEC`:** Systemd has dedicated error codes for setup failures. Code `203/EXEC` literally means: *"I could not find or run the executable file specified in `ExecStart`."*

**Evidence:** [evidence/07_invalid_configuration.png](evidence/07_invalid_configuration.png)

---

## Experiment 8: Repeated Crashes and Start Rate Limiting

### 1. Action
* Configured rapid crash behavior (`CRASH_AFTER=1`, `HEARTBEAT_INTERVAL=1`) and fast restart limits (`RestartSec=1s`, `StartLimitIntervalSec=20s`, `StartLimitBurst=5`) in the service unit.
* Reloaded daemon (`sudo systemctl daemon-reload`) and started the service (`sudo systemctl restart testpress-worker`).
* Monitored status: `systemctl status testpress-worker`.

### 2. Expectation
* The service should crash repeatedly until hitting the burst threshold of 5 attempts, at which point systemd should trigger rate limiting and stop restarting.

### 3. Observation
* The service restarted 5 times in rapid succession (`restart counter is at 5`).
* Upon the 5th failure, systemd logged:
  * `testpress-worker.service: Start request repeated too quickly.`
  * `testpress-worker.service: Failed with result 'exit-code'.`
  * `Failed to start Testpress Background Worker Service.`
* The service entered a permanent `failed` state and ceased restart attempts.

### 4. Explanation
* **The Circuit Breaker:** If a broken service crashes every single second, restarting it endlessly would burn 100% of your CPU and flood your disk with logs.
* **Protecting the System:** Systemd acts like an electrical circuit breaker. Because the service crashed 5 times in under 20 seconds, systemd stepped in and declared: *"This service is stuck in a crash loop, so I am stopping it before it degrades the whole server."*
* **Resetting the Breaker:** Once the underlying issue is fixed, an administrator must manually reset the circuit breaker using `systemctl reset-failed`.

**Evidence:** [evidence/08_repeated_crashes.png](evidence/08_repeated_crashes.png)

---

## Experiment 9: Resource Limits and Out-Of-Memory (OOM) Killer

### 1. Action
* Configured cgroup resource constraints in `/etc/systemd/system/testpress-worker.service`:
  * `MemoryMax=50M`
  * `CPUQuota=50%`
* Applied changes: `sudo systemctl daemon-reload && sudo systemctl restart testpress-worker`.
* Verified applied cgroup limits: `systemctl show testpress-worker -p MemoryMax -p CPUQuotaPerSecUSec`.
* Triggered excess memory allocation (100 MB) via trigger file: `touch /tmp/leak_memory && rm -f /tmp/leak_memory`.
* Inspected service status and systemd journal: `systemctl status testpress-worker` and `journalctl -u testpress-worker -n 25 --no-pager`.

### 2. Expectation
* Attempting to allocate 100 MB while restricted to a 50 MB hard ceiling (`MemoryMax=50M`) should breach the cgroup memory limit.
* The Linux kernel's Out-Of-Memory (OOM) Killer should terminate the offending process with `SIGKILL` (signal 9).
* Systemd should detect the OOM event (`result='oom-kill'`), log the violation, and automatically revive the service under `Restart=on-failure`.

### 3. Observation
* `systemctl show` verified enforcement: `MemoryMax=52428800` (50 MB) and `CPUQuotaPerSecUSec=500ms` (50% CPU).
* `systemctl status` showed cgroup memory tracking: `Memory: 5.4M (max: 50.0M available: 44.5M)`.
* Upon allocation trigger, journald logged:
  * `ALLOCATING MEMORY: Attempting to allocate 100 MB...`
  * `systemd[1]: testpress-worker.service: A process of this unit has been killed by the OOM killer.`
  * `systemd[1]: testpress-worker.service: Main process exited, code=killed, status=9/KILL`
  * `systemd[1]: testpress-worker.service: Failed with result 'oom-kill'.`
* Systemd scheduled a restart and successfully spawned a new process (`PID: 714244`), resuming normal operation.

### 4. Explanation
* **Setting a RAM Budget (cgroups):** In Linux, `cgroups` (control groups) act like a hard budget for system resources. Setting `MemoryMax=50M` tells the Linux kernel: *"Do not let this service use more than 50 MB of RAM under any circumstance."*
* **What happens when the budget is exceeded:** When our Python script tried to allocate 100 MB, it blew straight past its 50 MB limit.
* **The OOM Killer steps in:** To protect the rest of the operating system from freezing or running out of memory, the Linux kernel activated its **Out-Of-Memory (OOM) Killer**. It immediately killed our process with `SIGKILL` (signal 9).
* **Automatic Recovery:** Systemd detected that the process died due to an OOM kill (`result='oom-kill'`). Under `Restart=on-failure`, systemd waited 5 seconds and automatically started a fresh worker with a clean slate of memory.

**Evidence:** [evidence/09_resource_limits.png](evidence/09_resource_limits.png)


---

## Experiment 10: Automatic Service Startup on Server Reboot (Reboot Persistence)

### 1. Action
* Executed a full cold reboot of the Linux environment (`wsl --shutdown`).
* Reopened the terminal and verified uptime and service state:
  * `uptime -s && uptime -p`
  * `systemctl status testpress-worker`

### 2. Expectation
* Because the unit is enabled (`WantedBy=multi-user.target`), systemd should automatically launch `testpress-worker` during boot without requiring any manual start command.

### 3. Observation
* The system booted at `08:26:32` (`up 0 minutes`).
* `systemctl status` confirmed the service was already `active (running)` with PID `337`, having started automatically at `08:26:38` (just 6 seconds after boot).
* Heartbeats were actively emitting without human intervention.

### 4. Explanation
* **How Boot Targets Work:** When Linux boots, systemd initializes the system in phases called "targets". Once foundational services are ready, systemd reaches `multi-user.target` (standard multi-user system state).
* **The Enabled Symlink:** Running `sudo systemctl enable testpress-worker` created a symbolic link in `/etc/systemd/system/multi-user.target.wants/`. During boot, systemd scans this folder and launches all linked services automatically.

**Evidence:** [evidence/10_reboot_persistence.png](evidence/10_reboot_persistence.png)
