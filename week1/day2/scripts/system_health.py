#!/usr/bin/env python3
"""System health checker — the kind of script DevOps engineers write to monitor servers."""

import subprocess
import json
import datetime


def check_disk():
    """Run df -h, warn if any partition is over 80% full."""
    result = subprocess.run(["df", "-h"], capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")
    
    problems = []
    for line in lines[1:]:              # skip the header row
        parts = line.split()
        if len(parts) >= 5:
            usage = parts[4]            # the "Use%" column like "49%"
            mount = parts[5]            # where it's mounted like "/"
            percent = int(usage.replace("%", ""))
            if percent > 80:
                problems.append(f"{mount} is at {percent}%")
    
    return {"status": "OK" if not problems else "WARNING", "problems": problems}


def check_memory():
    """Run free -m, report used vs total."""
    result = subprocess.run(["free", "-m"], capture_output=True, text=True)
    mem_line = result.stdout.strip().split("\n")[1]   # "Mem:" row
    parts = mem_line.split()
    total = int(parts[1])
    used = int(parts[2])
    
    return {"total_mb": total, "used_mb": used, "percent": round(used / total * 100, 1)}


def check_services(services):
    """Check if each service is running using systemctl."""
    results = {}
    for svc in services:
        result = subprocess.run(
            ["systemctl", "is-active", svc],
            capture_output=True, text=True
        )
        results[svc] = result.stdout.strip()   # "active" or "inactive"
    return results


def main():
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "disk": check_disk(),
        "memory": check_memory(),
        "services": check_services(["ssh", "cron"])
    }
    
    # Print it nicely
    print(json.dumps(report, indent=2))
    
    # Save to file
    with open("/tmp/health_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nSaved to /tmp/health_report.json")


if __name__ == "__main__":
    main()