#!/bin/bash
yum install -y nginx
systemctl enable nginx
systemctl start nginx

# Get the instance ID from the metadata service
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)
AZ=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/placement/availability-zone)

# Replace the default nginx welcome page with one showing this instance's identity
cat > /usr/share/nginx/html/index.html <<EOF
<!DOCTYPE html>
<html>
<head><title>${INSTANCE_ID}</title></head>
<body style="font-family: sans-serif; padding: 40px;">
  <h1>Hello from ${INSTANCE_ID}</h1>
  <p>Availability Zone: ${AZ}</p>
</body>
</html>
EOF