#!/usr/bin/env python3
"""EC2 Inventory Lister - Lists all EC2 instances with key details."""

import boto3


def get_instance_name(tags):
    """Extract the Name tag from a list of tags.
    
    Tags are a list of dicts like [{"Key": "Name", "Value": "my-server"}].
    If no Name tag exists, return a placeholder.
    """
    if tags is None:
        return "(no name)"
    for tag in tags:
        if tag["Key"] == "Name":
            return tag["Value"]
    return "(no name)"


def list_ec2_instances():
    """Fetch and display all EC2 instances."""
    ec2 = boto3.client("ec2")
    response = ec2.describe_instances()

    instances = []

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append({
                "id": instance["InstanceId"],
                "name": get_instance_name(instance.get("Tags")),
                "state": instance["State"]["Name"],
                "type": instance["InstanceType"],
                "public_ip": instance.get("PublicIpAddress", "N/A"),
                "private_ip": instance.get("PrivateIpAddress", "N/A"),
                "launch_time": instance["LaunchTime"].strftime("%Y-%m-%d %H:%M"),
            })

    if not instances:
        print("No EC2 instances found.")
        return

    # Print header
    print(f"\n{'ID':<22} {'Name':<20} {'State':<12} {'Type':<12} {'Public IP':<16} {'Private IP':<16} {'Launched'}")
    print("-" * 120)

    for inst in instances:
        print(f"{inst['id']:<22} {inst['name']:<20} {inst['state']:<12} {inst['type']:<12} {inst['public_ip']:<16} {inst['private_ip']:<16} {inst['launch_time']}")

    print(f"\nTotal instances: {len(instances)}")


if __name__ == "__main__":
    list_ec2_instances()