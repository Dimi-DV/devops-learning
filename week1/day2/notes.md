# Day 2 - Linux Process Management & SSH Troubleshooting

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

---
Date: 2025-02-18
Status: ✅ Completed Day 2 exercises