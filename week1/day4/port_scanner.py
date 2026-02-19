import socket

for i in list(range(20, 26)) + list(range(70, 91)):
    sock = socket.socket()
    sock.settimeout(0.5)
    result = sock.connect_ex(("scanme.nmap.org", i))
    if result == 0:
        print(f"Port {i} is open")
    sock.close()
