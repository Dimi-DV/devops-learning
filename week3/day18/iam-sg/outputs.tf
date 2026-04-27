output "role_arn" {
  description = "ARN of the EC2 application role"
  value       = aws_iam_role.app_role.arn
}

output "role_name" {
  description = "Name of the EC2 application role"
  value       = aws_iam_role.app_role.name
}

output "instance_profile_name" {
  description = "Name of the instance profile to attach to EC2"
  value       = aws_iam_instance_profile.app.name
}

output "security_group_id" {
  description = "ID of the application security group"
  value       = aws_security_group.web.id
}

output "s3_bucket_name" {
  value = aws_s3_bucket.app_logs.id
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "alarm_name" {
  value = aws_cloudwatch_metric_alarm.high_cpu.alarm_name
}