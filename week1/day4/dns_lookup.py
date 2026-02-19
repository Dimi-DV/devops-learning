import dns.resolver

domains = ["google.com", "github.com"]

for domain in domains:
    print(f"\n--- {domain} ---")

    try:
        answers = dns.resolver.resolve(domain, "A")
        for rdata in answers:
            print(f"{domain} has A record {rdata.address}")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        print(f"{domain} has no A record")

    try:
        answers = dns.resolver.resolve(domain, "MX")
        for rdata in answers:
            print(f"{domain} has MX record {rdata.exchange}")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        print(f"{domain} has no MX record")

    try:
        answers = dns.resolver.resolve(domain, "CNAME")
        for rdata in answers:
            print(f"{domain} has CNAME record {rdata.target}")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        print(f"{domain} has no CNAME record")