output "alb_dns_name" {
  description = "Public DNS name of the ALB — visit this in a browser to test"
  value       = aws_lb.main.dns_name
}

output "alb_url" {
  description = "Full HTTP URL of the ALB"
  value       = "http://${aws_lb.main.dns_name}"
}

output "alb_logs_bucket" {
  description = "S3 bucket where ALB access logs are stored"
  value       = aws_s3_bucket.alb_logs.id
}

output "instance_role_arn" {
  description = "ARN of the IAM role attached to ASG instances"
  value       = aws_iam_role.app_role.arn
}

output "instance_profile_name" {
  description = "Instance profile name (used by the launch template)"
  value       = aws_iam_instance_profile.app.name
}

output "asg_name" {
  description = "Auto Scaling Group name"
  value       = aws_autoscaling_group.app.name
}

output "target_group_arn" {
  description = "ARN of the target group registered with the ALB"
  value       = aws_lb_target_group.app.arn
}

output "vpc_id" {
  description = "ID of the VPC (passed through from module)"
  value       = module.vpc.vpc_id
}

output "sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms"
  value       = aws_sns_topic.alerts.arn
}