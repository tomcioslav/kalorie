# terraform/lightsail.tf
data "aws_availability_zones" "available" {
  state = "available"
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

resource "aws_lightsail_static_ip" "this" {
  name = "calorie-tracker-ip"
}

locals {
  sslip_hostname = "${replace(aws_lightsail_static_ip.this.ip_address, ".", "-")}.sslip.io"
  public_mcp_url = "https://${local.sslip_hostname}/mcp"

  launch_script = templatefile("${path.module}/scripts/launch.sh.tpl", {
    usda_api_key          = var.usda_api_key
    cognito_region        = var.aws_region
    cognito_user_pool_id  = aws_cognito_user_pool.this.id
    cognito_app_client_id = aws_cognito_user_pool_client.this.id
    public_mcp_url        = local.public_mcp_url
    sslip_hostname        = local.sslip_hostname
  })
}

resource "aws_lightsail_instance" "this" {
  name              = "calorie-tracker"
  availability_zone = data.aws_availability_zones.available.names[0]
  blueprint_id      = "ubuntu_24_04"
  bundle_id         = "micro_3_0"
  # Lightsail's user_data field is documented as accepting a single-lined
  # script (unlike EC2's multi-line cloud-init), and real reports of
  # multi-line user_data trouble on Lightsail back that up -- so the actual
  # multi-line script above gets base64-encoded into one line here instead
  # of passed as-is.
  user_data = "umask 077 && echo ${base64encode(local.launch_script)} | base64 --decode > /tmp/launch.sh && bash /tmp/launch.sh"

  add_on {
    type          = "AutoSnapshot"
    status        = "Enabled"
    snapshot_time = "04:00"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_lightsail_static_ip_attachment" "this" {
  static_ip_name = aws_lightsail_static_ip.this.name
  instance_name  = aws_lightsail_instance.this.name
}

resource "aws_lightsail_instance_public_ports" "this" {
  instance_name = aws_lightsail_instance.this.name

  # Port 22 is required even though redeploys use Lightsail's browser SSH
  # console, not a raw internet-facing SSH client -- AWS's browser console
  # still connects to the instance's real port 22, just proxied through
  # AWS's own infrastructure (confirmed directly, not assumed -- the older
  # design doc's assumption that browser SSH needs no firewall rule is
  # wrong).
  #
  # cidrs/ipv6_cidrs/cidr_list_aliases are pinned explicitly (matching
  # AWS's own default of "open to everywhere") rather than left unset --
  # they're Optional+Computed inside a Set-typed block, and leaving them
  # unset makes Terraform hash the config's port_info differently from the
  # applied state's port_info, producing a perpetual "must be replaced"
  # diff (destroying and recreating the whole firewall) on every future
  # plan even with zero real changes. Confirmed directly against the
  # provider schema and a real post-apply plan.
  port_info {
    protocol          = "tcp"
    from_port         = 22
    to_port           = 22
    cidrs             = ["0.0.0.0/0"]
    ipv6_cidrs        = ["::/0"]
    cidr_list_aliases = []
  }
  port_info {
    protocol          = "tcp"
    from_port         = 80
    to_port           = 80
    cidrs             = ["0.0.0.0/0"]
    ipv6_cidrs        = ["::/0"]
    cidr_list_aliases = []
  }
  port_info {
    protocol          = "tcp"
    from_port         = 443
    to_port           = 443
    cidrs             = ["0.0.0.0/0"]
    ipv6_cidrs        = ["::/0"]
    cidr_list_aliases = []
  }
}
