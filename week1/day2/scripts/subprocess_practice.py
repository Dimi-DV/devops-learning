```python
import subprocess
import math
result = subprocess.run(["df", "-h"], capture_output=True, text=True)
print(result.stdout)
result = subprocess.run(["free", "-m"], capture_output=True, text=True)
lines = result.stdout.split("\n")
print("Full output:")
print(result.stdout)
print("Just memory line:")
print(lines[1])
"""exercise 3"""
result = subprocess.run(["systemctl", "status", "nginx"], capture_output=True, text=True)
print(result.stdout)
"""exercise 4"""
s = subprocess.run(["uptime"], capture_output=True, text=True).stdout
print(s.split("load average:")[-1].strip() if "load average:" in s else s.split("load averages:")[-1].strip())
```
