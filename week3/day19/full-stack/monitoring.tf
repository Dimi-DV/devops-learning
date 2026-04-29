# SNS topic — the alert channel
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"

  tags = {
    Project = var.project_name
  }
}

# Email subscription to the topic
resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# CloudWatch alarm — fires when ALB host is unhealthy
resource "aws_cloudwatch_metric_alarm" "unhealthy_host" {
  alarm_name          = "${var.project_name}-unhealthy-host"
  alarm_description   = "Triggers when an instance has been unhealthy for 2 minutes straight"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  dimensions          = { TargetGroup = aws_lb_target_group.app.arn_suffix, LoadBalancer = aws_lb.main.arn_suffix }
  period              = 60
  threshold           = 0
  statistic           = "Maximum"

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = {
    Project = var.project_name
  }
}