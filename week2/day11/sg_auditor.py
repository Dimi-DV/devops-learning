#!/usr/bin/env python3
"""Security Group Auditor - Flags security groups with SSH open to the world."""

import boto3


def is_port_exposed(permission, target_port=22):
    """Check if a specific port is included in this permission's port range.
    
    Handles three cases:
    - IpProtocol "-1" means ALL traffic (all ports, all protocols)
    - Exact port match (FromPort == ToPort == 22)
    - Port range that includes 22 (e.g., FromPort=0, ToPort=65535)
    """
    # Protocol "-1" = all traffic, all ports
    if permission.get("IpProtocol") == "-1":
        return True

    from_port = permission.get("FromPort", 0)
    to_port = permission.get("ToPort", 0)

    return from_port <= target_port <= to_port


def check_open_sources(permission):
    """Return list of dangerous source CIDRs (0.0.0.0/0 or ::/0)."""
    dangerous_sources = []

    for ip_range in permission.get("IpRanges", []):
        if ip_range["CidrIp"] == "0.0.0.0/0":
            dangerous_sources.append("0.0.0.0/0")

    for ipv6_range in permission.get("Ipv6Ranges", []):
        if ipv6_range["CidrIpv6"] == "::/0":
            dangerous_sources.append("::/0")

    return dangerous_sources


def audit_security_groups():
    """Check all security groups for SSH exposed to the world."""
    ec2 = boto3.client("ec2")
    response = ec2.describe_security_groups()

    findings = []

    for sg in response["SecurityGroups"]:
        for permission in sg["IpPermissions"]:
            if is_port_exposed(permission, target_port=22):
                dangerous_sources = check_open_sources(permission)
                if dangerous_sources:
                    findings.append({
                        "group_id": sg["GroupId"],
                        "group_name": sg["GroupName"],
                        "vpc_id": sg.get("VpcId", "N/A"),
                        "sources": dangerous_sources,
                        "protocol": permission.get("IpProtocol", "all"),
                        "port_range": f"{permission.get('FromPort', 'all')}-{permission.get('ToPort', 'all')}",
                    })

    # Report
    print("\n" + "=" * 70)
    print("SECURITY GROUP AUDIT: SSH (Port 22) Open to World")
    print("=" * 70)

    if not findings:
        print("\n✅ No security groups have SSH open to 0.0.0.0/0 or ::/0")
        print("   All clear!")
    else:
        print(f"\n⚠️  Found {len(findings)} security group(s) with SSH exposed:\n")
        for f in findings:
            print(f"  🔴 {f['group_id']} ({f['group_name']})")
            print(f"     VPC: {f['vpc_id']}")
            print(f"     Port range: {f['port_range']} ({f['protocol']})")
            print(f"     Open to: {', '.join(f['sources'])}")
            print()

    # Summary
    total_sgs = len(response["SecurityGroups"])
    print(f"Scanned {total_sgs} security groups total.")

    return findings


if __name__ == "__main__":
    audit_security_groups()