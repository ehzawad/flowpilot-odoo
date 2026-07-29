variable "project_name" {
  type    = string
  default = "flowpilot"
}

variable "environment" {
  type    = string
  default = "pilot"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "database_name" {
  type    = string
  default = "flowpilot"
}

variable "database_username" {
  type    = string
  default = "flowpilot"
}

variable "database_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "database_allocated_storage_gb" {
  type    = number
  default = 30
}

variable "database_multi_az" {
  type    = bool
  default = false
}

variable "monthly_budget_usd" {
  type    = number
  default = 150
}

variable "budget_notification_email" {
  type      = string
  default   = ""
  sensitive = true
}
