# Day 2 — Linux Processes, Services, and Logs

## What I Learned

### Process Management
- **Processes**: Running programs with unique PIDs
- **ps aux**: Shows all processes with CPU/memory usage
- **top/htop**: Live process monitoring (htop is better)
- **kill**: Send signals to processes
  - `kill <PID>` = SIGTERM (graceful)
  - `kill -9 <PID>` = SIGKILL (force)
- **Background processes**: Use `&` to run in background
  - `Ctrl+Z` = suspend, `bg` = resume in background, `fg` = bring to foreground
  - `jobs` = list background jobs
- **nohup**: Keep processes running after logout

### SSH Troubleshooting
- Fixed SSH connection timeout to VM
- Problem: SSH service not running + IP changed
- Solution: `sudo systemctl start ssh` and used correct IP
- Learned: Check service status with `systemctl status <service>`
- Set up `~/.ssh/config` for easier connections

### Commands I Can Now Use
```bash
ps aux | grep <process>
top
htop
kill <PID>
sleep 100 &
jobs
bg / fg
nohup <command> &
sudo systemctl status ssh
systemctl start/stop/restart/enable <service>
```

## Troubleshooting Skills
- When SSH fails: access VM console directly (UTM)
- Check if services are running before assuming network issues
- Bridged networking = IP can change on reboot


### Processes
- Every running program is a process with a PID
- `ps aux` shows all processes — key columns: PID, %CPU, %MEM, COMMAND
- `htop` gives an interactive view (installed with `sudo apt install htop`)
- `kill <PID>` sends SIGTERM (graceful), `kill -9 <PID>` sends SIGKILL (force)
- Background processes: `&` to run in background, `jobs` to list, `fg`/`bg` to manage
- `Ctrl+Z` suspends a foreground process

### systemd and Services
- systemd is PID 1 — the init system that manages all services on Ubuntu
- `systemctl status <service>` — check if running, see PID, read recent logs
- `systemctl start/stop/restart <service>` — control services
- `systemctl enable/disable <service>` — control boot behavior
- `daemon-reload` required after creating or editing unit files

### Unit Files
- Custom services go in `/etc/systemd/system/`
- Three sections: [Unit] (metadata), [Service] (how to run), [Install] (boot behavior)
- Key fields: ExecStart, Restart, User, WorkingDirectory, Type=simple
- `StandardOutput=journal` routes print() to journalctl

### journalctl (Log Reading)
- `journalctl -u <service>` — logs for a specific service
- `journalctl -u <service> -f` — follow in real-time
- `journalctl -n 50` — last 50 lines
- `journalctl -b` — logs from current boot

## Hands-On Work
- Built `timestamp_logger.py` — Python script that writes timestamps to `/tmp/timestamp_service.log` every 10 seconds
- Created a systemd unit file to run it as a managed service
- Debugged a crash-loop issue — service was starting and immediately failing, used `journalctl` to diagnose
- Tested `Restart=on-failure` behavior — watched systemd auto-restart after killing the process
- Verified service survived reboot with `systemctl enable`

## Key Takeaways
- `systemctl status` + `journalctl` are the first tools you reach for when a service misbehaves
- Always test scripts manually before wrapping them in a service
- Typos in filenames cause "file not found" errors that look like bigger problems (timestamp_service vs timestamp_services)
- Unit file paths must be absolute, and User field must match an actual system user

## Package Management (apt)

### Core Commands
- `sudo apt update` — refresh package index (always run first)
- `sudo apt upgrade -y` — install available upgrades
- `sudo apt install <package>` — install new packages
- `sudo apt remove <package>` — remove (keeps config)
- `sudo apt purge <package>` — remove everything including config
- `sudo apt autoremove` — clean up orphaned dependencies
- `apt search <name>` — find packages
- `apt list --installed` — see what's installed

### Where Packages Come From
- `/etc/apt/sources.list` — main repository list
- `/etc/apt/sources.list.d/` — additional repos (PPAs, third-party)
- Components: main, restricted, universe, multiverse
- PPAs: third-party repos via `add-apt-repository`

### Useful Tools Installed
- `tree` — visual directory structure
- `jq` — JSON parser (critical for AWS CLI output)
- `curl` — HTTP requests
- `nmap` — port scanning

## Cron (Scheduled Tasks)

### Syntax
```
* * * * * command
│ │ │ │ └─ day of week (0-6)
│ │ │ └─── month (1-12)
│ │ └───── day of month (1-31)
│ └─────── hour (0-23)
└───────── minute (0-59)
```

### Key Commands
- `crontab -e` — edit your cron jobs
- `crontab -l` — list current jobs
- `*/5 * * * *` — every 5 minutes
- Always use absolute paths in cron jobs
- Debug with `grep CRON /var/log/syslog`

### Hands-On
- Created `system_snapshot.sh` — logs disk + memory usage
- Scheduled with cron to run every 5 minutes
- Verified multiple snapshots appearing in log file

---
Date: 2025-02-18
Status: ✅ Completed Day 2 exercises