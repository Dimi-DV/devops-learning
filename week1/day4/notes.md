# Day 4: HTTP, TLS, Firewalls, Python Networking

## HTTP
- Request structure: method + path + headers + optional body
- Methods: GET (read), POST (create), PUT (replace), DELETE (remove)
- POST is non-idempotent — repeating it creates duplicate records
- Key headers: Host, Content-Type, Authorization, Location, Cache-Control
- Status codes: 2xx success, 3xx redirect, 4xx client error, 5xx server error
- 401 = not authenticated, 403 = authenticated but not allowed
- Cookies maintain state across stateless HTTP connections

## TLS
- Handles encryption, authentication, and integrity
- Handshake: ClientHello → ServerHello → certificate → key exchange → encrypted tunnel
- Certificate contains: issuer, validity dates, domain (CN), public key
- Wildcard cert (*.google.com) covers all subdomains
- ALB handles TLS termination — backend only sees plain HTTP on port 80
- ACM issues and auto-renews certificates for AWS resources

## Firewalls
- UFW is a wrapper around iptables — default deny incoming, allow outgoing
- Stateful (security groups): response traffic automatically allowed
- Stateless (NACLs): must explicitly allow both directions including ephemeral ports
- Security groups operate at hypervisor level — traffic never reaches instance
- UFW localhost limitation: loopback traffic bypasses firewall rules

## Python Scripts
- requests library = curl in Python, response is an object with .status_code, .elapsed, .headers, .text
- socket.connect_ex() returns 0 if port open, non-zero if closed
- dns.resolver.resolve(domain, "A/MX/CNAME") queries DNS records
- try/except catches NoAnswer and NXDOMAIN for missing record types

## Key Observations
- X-Amzn-Trace-Id header injected by ALB proves traffic goes through it
- Multiple IPs in DNS response = load balancer with multi-AZ redundancy
- github.com MX records point to Google — outsources email to Google Workspace
- CNAMEs cannot exist on root domains, only subdomains