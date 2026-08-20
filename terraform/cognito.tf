resource "aws_cognito_user_pool" "this" {
  name = "calorie-tracker"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "calorie-tracker-726024099471"
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_user_pool_client" "this" {
  name         = "claude-connector"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  # Must cover everything Cognito's own OIDC discovery document advertises
  # in scopes_supported ("openid", "email", "phone", "profile") -- a
  # narrower list here caused a real invalid_scope rejection the moment
  # Claude's connector requested "profile" in addition to what the
  # discovery doc offered, confirmed directly against the live pool.
  allowed_oauth_scopes         = ["openid", "email", "phone", "profile"]
  callback_urls                = ["https://claude.ai/api/mcp/auth_callback"]
  supported_identity_providers = ["COGNITO"]

  explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "random_password" "cognito_temp" {
  for_each = toset(var.cognito_users)

  length      = 16
  special     = true
  min_upper   = 1
  min_lower   = 1
  min_numeric = 1
  # Cognito's temp-password character set is narrower than random_password's
  # full default set -- restrict to characters Cognito accepts so apply
  # doesn't fail on an unlucky random symbol.
  override_special = "!@#$%^&*()_+-="
}

resource "aws_cognito_user" "household" {
  for_each = toset(var.cognito_users)

  user_pool_id = aws_cognito_user_pool.this.id
  username     = each.value
  temporary_password = lookup(
    var.cognito_temp_passwords,
    each.value,
    random_password.cognito_temp[each.value].result,
  )
  desired_delivery_mediums = ["EMAIL"]

  attributes = {
    email          = each.value
    email_verified = true
  }
}
