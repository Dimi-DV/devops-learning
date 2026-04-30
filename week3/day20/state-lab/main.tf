moved {
    from = aws_s3_bucket.primary
    to = aws_s3_bucket.managed
}

resource "aws_s3_bucket" "managed" {
  bucket        = "dimitrije-state-lab-managed-2026"

  tags = {
    name        = "managed-by-terraform"
    environment = "lab"
    ManualOwner = "alice"
  }
}