variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "eu-central-1"
}

variable "usda_api_key" {
  description = "USDA FoodData Central API key (free: https://api.data.gov/signup). Left as the default, the app falls back to the rate-limited DEMO_KEY."
  type        = string
  sensitive   = true
  default     = "DEMO_KEY"
}

variable "cognito_users" {
  description = "Household members who get a Cognito account."
  type        = list(string)
  default     = ["joanna.kolbuc@gmail.com", "tomek.juszczyszyn@gmail.com"]
}

variable "cognito_temp_passwords" {
  description = "Optional per-user override for a Cognito account's initial temporary password (key = the email from cognito_users). Any user not listed here still gets a random one generated automatically. Set in terraform.tfvars, never here -- it's gitignored."
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "budget_limit_usd" {
  description = "Monthly spend threshold that triggers a budget alert email."
  type        = number
  default     = 15
}

variable "budget_alert_email" {
  description = "Email address for budget alerts."
  type        = string
  default     = "tomek.juszczyszyn@gmail.com"
}
