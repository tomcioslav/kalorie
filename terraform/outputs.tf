output "static_ip" {
  value = aws_lightsail_static_ip.this.ip_address
}

output "public_mcp_url" {
  value = local.public_mcp_url
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "cognito_app_client_id" {
  value = aws_cognito_user_pool_client.this.id
}

output "cognito_hosted_ui_domain" {
  value = "${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "cognito_temp_passwords" {
  # Mirrors cognito.tf's own lookup() so this always shows the password that
  # actually got set -- an overridden one from cognito_temp_passwords, or the
  # random fallback -- never the random value alone if it was overridden.
  value = {
    for u in var.cognito_users :
    u => lookup(var.cognito_temp_passwords, u, random_password.cognito_temp[u].result)
  }
  sensitive = true
}
