output "bucket_name" {
    value       = aws_s3_bucket.first_bucket.id
    description = "name of the s3 bucket"
}

output "bucket_arn" {
  value       = aws_s3_bucket.first_bucket.arn
  description = "ARN of the S3 bucket"
}

output "bucket_region" {
  value       = aws_s3_bucket.first_bucket.region
  description = "Region of the S3 bucket"
}