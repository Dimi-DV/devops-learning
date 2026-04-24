output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = [for s in aws_subnet.public : s.id]
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = [for s in aws_subnet.private : s.id]
}

output "web_sg_id" {
  description = "ID of the web security group"
  value       = aws_security_group.web.id
}

output "private_sg_id" {
  description = "ID of the private security group"
  value       = aws_security_group.private.id
}

output "nat_gateway_id" {
  description = "ID of the NAT gateway, or null if not created"
  value       = var.create_nat ? aws_nat_gateway.main[0].id : null
}