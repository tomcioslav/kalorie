# Calorie Tracker — Infrastructure

## Prerequisites

- AWS credentials configured (`aws sts get-caller-identity` should show
  account `726024099471`, user `terraform-calorie-tracker`).
- `cp terraform.tfvars.example terraform.tfvars` and fill in a real
  `usda_api_key` (free key: https://api.data.gov/signup). Without this,
  the deployed server falls back to the heavily rate-limited `DEMO_KEY`.

`tomcioslav/kalorie` is a public repo, so the instance clones it over
plain HTTPS with no credentials at all — no GitHub token, no deploy key,
nothing GitHub-related to configure here. If the repo is ever made
private, a deploy key (or some other auth mechanism) would need to be
reintroduced into `lightsail.tf`/`scripts/launch.sh.tpl` and the clone
switched back to SSH.

## First-time setup

The state bucket is bootstrapped once, separately, with local state:

```bash
cd bootstrap
terraform init
terraform apply
cd ..
```

The bootstrap has already been run once for this project (the state
bucket already exists) — re-running `terraform apply` there is
idempotent and safe, but its state lives only on whichever machine ran
it (it is not backed up anywhere), so importing/re-bootstrapping would
be needed if that machine is ever lost.

Then the real infrastructure:

```bash
terraform init
terraform plan   # review carefully -- this creates a real, billed,
                  # public-facing Lightsail instance and a real Cognito
                  # user pool with a public login page
terraform apply
```

After `apply`:
- SSH into the instance via Lightsail's browser console (AWS Console →
  Lightsail → the `calorie-tracker` instance → Connect) and check
  `/var/log/calorie-tracker-launch.log`, and confirm
  `/var/log/calorie-tracker-launch-complete` exists — the launch script
  has not been tested end-to-end before this first real apply (see the
  plan this was built from), so this is the first real check that it
  worked.
- Before assuming everything works, run
  `curl -sSf https://$(terraform output -raw static_ip | tr . -).sslip.io/.well-known/oauth-protected-resource`
  and confirm it returns JSON (not a connection error or a certificate
  error). Caddy's first TLS certificate request happens at boot, on the
  instance's temporary dynamic IP, before the static IP is attached, so
  there's a small chance the very first request needs a retry (Caddy
  retries automatically; this curl check just confirms it settled).
- `terraform output public_mcp_url` gives the exact URL to enter as the
  connector address in Claude.
- Add the app client ID from `terraform output cognito_app_client_id` to
  Claude's custom connector setup as the OAuth client ID.
- Cognito's temporary passwords expire after 7 days (Cognito's default
  `temporary_password_validity_days`) — if a household member doesn't
  log in within a week, a fresh temporary password is needed (e.g. via
  `aws cognito-idp admin-create-user` with `--message-action RESEND`, or
  `terraform apply -replace` on that user, or read `terraform output
  cognito_temp_passwords` again if it's still valid).

## Redeploying app-code changes

No CI/CD yet — after pushing new commits to `main`:

```bash
# From the Lightsail browser SSH console — run as root (the console logs
# in as a non-root user, and /opt/calorie-tracker is only readable by
# root):
sudo -i
cd /opt/calorie-tracker
git pull
uv sync --frozen
sudo systemctl restart calorie-tracker
```

## Data loss warning

Changing `usda_api_key`, the launch script, or the instance's
blueprint/bundle/availability-zone forces Terraform to destroy and
recreate the Lightsail instance, which takes the SQLite database with
it — the AutoSnapshot add-on does NOT survive instance deletion (AWS
deletes automatic snapshots when their source instance is deleted). The
instance has `prevent_destroy` set as a safety net, but if you ever need
to intentionally replace it, take a manual snapshot first.

The same applies to `terraform destroy` in the "Tearing down" section
below — it deletes the instance, the database, all snapshots, and the
Cognito user pool with all accounts.

## Tearing down

The Lightsail instance has `prevent_destroy` set (see "Data loss
warning" above), so a plain `terraform destroy` will refuse to remove it
with `Error: Instance cannot be destroyed ... has lifecycle.prevent_destroy
set`. That's deliberate — remove or comment out the `lifecycle` block in
`lightsail.tf` first if you actually mean to tear everything down:

```bash
terraform destroy
```

This does not remove the bootstrap S3 state bucket (`cd bootstrap &&
terraform destroy` separately, if ever truly done with this project).
See the "Data loss warning" above before running this.
