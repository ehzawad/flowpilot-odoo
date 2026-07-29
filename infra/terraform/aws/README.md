# AWS foundation

This Terraform module provisions the stateful and security-sensitive foundation for FlowPilot:
VPC/subnets, encrypted RDS PostgreSQL, ECR repositories, S3 artifacts, an SQS queue and dead-letter
queue, Secrets Manager, CloudWatch, and a monthly budget. It deliberately does not create a bespoke
Kubernetes cluster. Apply `infra/k8s` to an existing EKS/GKE/AKS cluster, or add a separate cluster
module when a customer actually requires Kubernetes ownership.

```zsh
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
```

The generated RDS master password is stored in the RDS-managed Secrets Manager secret. Store
application secrets in the separate application secret; never put them in `terraform.tfvars`.
