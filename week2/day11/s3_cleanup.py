#!/usr/bin/env python3
"""S3 Bucket Checker - Finds buckets without versioning enabled."""

import boto3
from botocore.exceptions import ClientError


def check_bucket_versioning(s3_client, bucket_name):
    """Check versioning status for a single bucket.
    
    Returns: "Enabled", "Suspended", or "Disabled"
    
    The API returns {"Status": "Enabled"} or {"Status": "Suspended"}.
    If versioning was never turned on, the response has NO Status key.
    """
    try:
        response = s3_client.get_bucket_versioning(Bucket=bucket_name)
        status = response.get("Status", "Disabled")
        return status
    except ClientError as e:
        # This can happen if the bucket is in a region we can't reach,
        # or we don't have permission
        return f"Error: {e.response['Error']['Code']}"


def check_s3_buckets():
    """Audit all S3 buckets for versioning status."""
    s3 = boto3.client("s3")
    response = s3.list_buckets()
    buckets = response.get("Buckets", [])

    if not buckets:
        print("No S3 buckets found in this account.")
        return []

    results = []

    for bucket in buckets:
        name = bucket["Name"]
        created = bucket["CreationDate"].strftime("%Y-%m-%d")
        versioning = check_bucket_versioning(s3, name)

        results.append({
            "name": name,
            "created": created,
            "versioning": versioning,
        })

    # Report
    print("\n" + "=" * 70)
    print("S3 BUCKET AUDIT: Versioning Status")
    print("=" * 70)

    unversioned = [r for r in results if r["versioning"] != "Enabled"]

    if unversioned:
        print(f"\n⚠️  {len(unversioned)} bucket(s) without versioning:\n")
        for b in unversioned:
            icon = "🔴" if b["versioning"] == "Disabled" else "🟡"
            print(f"  {icon} {b['name']}")
            print(f"     Created: {b['created']}")
            print(f"     Versioning: {b['versioning']}")
            print()
    
    versioned = [r for r in results if r["versioning"] == "Enabled"]
    if versioned:
        print(f"✅ {len(versioned)} bucket(s) with versioning enabled:")
        for b in versioned:
            print(f"   ✅ {b['name']}")

    print(f"\nTotal buckets scanned: {len(results)}")

    return results


if __name__ == "__main__":
    check_s3_buckets()