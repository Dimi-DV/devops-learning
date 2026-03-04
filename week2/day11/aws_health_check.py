#!/usr/bin/env python3
"""AWS Health Check - Combined infrastructure audit."""

import sys
from datetime import datetime

# Import our other scripts as modules
from ec2_inventory import list_ec2_instances
from sg_auditor import audit_security_groups
from s3_cleanup import check_s3_buckets


def run_health_check():
    """Run all audits and produce a combined report."""
    print("\n" + "=" * 70)
    print(f"  AWS INFRASTRUCTURE HEALTH CHECK")
    print(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # --- EC2 Inventory ---
    print("\n" + "─" * 70)
    print("  SECTION 1: EC2 INVENTORY")
    print("─" * 70)
    try:
        list_ec2_instances()
    except Exception as e:
        print(f"  ❌ EC2 check failed: {e}")

    # --- Security Group Audit ---
    print("\n" + "─" * 70)
    print("  SECTION 2: SECURITY GROUP AUDIT")
    print("─" * 70)
    try:
        sg_findings = audit_security_groups()
    except Exception as e:
        print(f"  ❌ SG audit failed: {e}")
        sg_findings = []

    # --- S3 Bucket Check ---
    print("\n" + "─" * 70)
    print("  SECTION 3: S3 BUCKET AUDIT")
    print("─" * 70)
    try:
        s3_results = check_s3_buckets()
    except Exception as e:
        print(f"  ❌ S3 check failed: {e}")
        s3_results = []

    # --- Summary ---
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    issues = 0

    if sg_findings:
        issues += len(sg_findings)
        print(f"  🔴 {len(sg_findings)} security group(s) with SSH open to world")

    unversioned = [r for r in s3_results if r.get("versioning") != "Enabled"]
    if unversioned:
        issues += len(unversioned)
        print(f"  🟡 {len(unversioned)} S3 bucket(s) without versioning")

    if issues == 0:
        print("  ✅ All checks passed — no issues found!")
    else:
        print(f"\n  Total issues: {issues}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    run_health_check()