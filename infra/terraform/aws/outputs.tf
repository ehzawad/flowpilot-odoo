output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = values(aws_subnet.private)[*].id
}

output "workload_security_group_id" {
  value = aws_security_group.workloads.id
}

output "database_endpoint" {
  value     = aws_db_instance.postgres.address
  sensitive = true
}

output "database_secret_arn" {
  value     = aws_db_instance.postgres.master_user_secret[0].secret_arn
  sensitive = true
}

output "application_secret_arn" {
  value = aws_secretsmanager_secret.application.arn
}

output "ecr_repository_urls" {
  value = { for name, repository in aws_ecr_repository.images : name => repository.repository_url }
}

output "artifact_bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "job_queue_url" {
  value = aws_sqs_queue.jobs.url
}
