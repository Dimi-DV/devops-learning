# Day 3 — Networking Fundamentals: IP, Subnets, DNS, TCP/IP

## What I Built / Did Today
- Solved 10 subnetting problems by hand
- Designed a 4-subnet VPC CIDR scheme (saved for Week 2 AWS build)
- Ran dig, dig +trace, nslookup against real domains
- Edited /etc/hosts to add a local override (mytest.local)
- Inspected /etc/resolv.conf and traced full DNS chain with resolvectl
- Used ss -tulnp to audit all listening ports on the VM
- Killed nginx (stopped + disabled) and Python HTTP server
- Ran nmap localhost to verify clean port state
- Traced live SSH connection with ss -tnp

## Key Concepts

### IP Addressing
- IPv4 = 32-bit number, written as 4 octets (0-255)
- /N = how many bits are locked as network, rest are host bits
- Usable hosts = 2^(host bits) - 2
- Bigger /N = smaller subnet

### Subnetting
- Block size = 2^(32-N)
- Network address = first in block (not usable)
- Broadcast = last in block (not usable)
- /24 = 254 hosts, /28 = 14 hosts, /16 = 65534 hosts

### Private IP Ranges
- 10.0.0.0/8       → enterprise, AWS VPCs
- 172.16.0.0/12    → mid-size, Docker default
- 192.168.0.0/16   → home routers

### VPC Design (Week 2 Build)
- Base: 10.0.0.0/16
- public-1a:  10.0.1.0/24  (or /23)
- public-1b:  10.0.2.0/24
- private-1a: 10.0.10.0/24
- private-1b: 10.0.11.0/24

### DNS Resolution Chain
1. Check local cache
2. Check /etc/hosts
3. Recursive resolver (127.0.0.53 → 180.222.193.202)
4. Root nameservers → who handles .com?
5. TLD nameservers → who handles domain.com?
6. Authoritative nameservers → here's the IP

### DNS Record Types
- A     → domain to IPv4
- CNAME → alias to another name
- MX    → mail servers
- NS    → authoritative nameservers
- TXT   → verification, SPF

### TTL
- How long resolvers cache answers (seconds)
- Lower TTL before DNS changes so they propagate faster

### Key Files
- /etc/hosts      → local overrides, bypasses DNS
- /etc/resolv.conf → which DNS server to query

### TCP vs UDP
- TCP = reliable, ordered, connection-based (HTTP, SSH, databases)
- UDP = fast, no guarantees (DNS, video streaming, gaming)

### TCP 3-Way Handshake
- SYN → SYN-ACK → ACK
- Must complete before any data flows
- Failed handshake = firewall/security group dropping packets

### Ports
- IP gets you to the server, port gets you to the service
- 22=SSH, 80=HTTP, 443=HTTPS, 53=DNS, 3306=MySQL, 5432=PostgreSQL
- 0.0.0.0 = listening on all interfaces
- 127.0.0.1 = localhost only (not externally reachable)

### Commands Used Today
- dig domain.com            # DNS lookup
- dig domain.com +trace     # full resolution chain
- dig domain.com MX/NS      # specific record types
- ss -tulnp                 # all listening ports (TCP+UDP)
- ss -tnp                   # established connections
- nmap localhost            # port scan
- resolvectl status         # upstream DNS servers
- systemctl stop/disable    # kill a service properly

## What Was Hard
- Remembering block size vs host count (they're different things)
- /26 block size is 64 not 4 — confused this initially
- /etc/hosts needed sudo to edit

## What Connects to AWS
- VPC CIDR design = exactly what I'll build in Week 2
- Security groups = port-based rules (same ports learned today)
- Route 53 = AWS DNS (same A/CNAME/MX concepts)
- ALB = reverse proxy pattern (like nginx/Cloudflare)
- AWS resolver = 169.254.169.253 (same role as 127.0.0.53 locally)