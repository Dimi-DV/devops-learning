data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app_role" {
  name               = "${var.project_name}-app-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

data "aws_iam_policy_document" "s3_read" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "s3_read" {
  name   = "${var.project_name}-s3-read"
  policy = data.aws_iam_policy_document.s3_read.json
}

resource "aws_iam_role_policy_attachment" "app_s3" {
  role       = aws_iam_role.app_role.name
  policy_arn = aws_iam_policy.s3_read.arn
}


data "aws_iam_policy_document" "cloudwatch_write" {
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "cloudwatch_write" {
  name   = "${var.project_name}-cloudwatch-write"
  policy = data.aws_iam_policy_document.cloudwatch_write.json
}

resource "aws_iam_role_policy_attachment" "app_cloudwatch" {
  role       = aws_iam_role.app_role.name
  policy_arn = aws_iam_policy.cloudwatch_write.arn
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-app-profile"
  role = aws_iam_role.app_role.name
}

