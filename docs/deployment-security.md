# Production deployment security

The deployment job uses native OpenSSH, verifies the server host key, and receives
SSH credentials in a job that runs no third-party actions. Build actions are
pinned to reviewed commit IDs. Deployment waits for the test suite and deploys
only the tested SHA, using a fast-forward update with no reset of server files.

Before enabling this workflow, configure the `production` GitHub environment
with HOST, USER, KEY, and SSH_KNOWN_HOSTS secrets. Obtain the host key through the
Droplet console or another trusted channel; verify the fingerprint before adding
the OpenSSH known_hosts entry. Do not trust an unverified ssh-keyscan result.
The workflow intentionally fails if the host identity is missing or mismatched.

Restrict environment access to main, require the security/test jobs in branch
protection, and protect workflow changes through code review. Restrict the deploy
SSH user to the required git/uv/service commands; do not grant unrestricted sudo.
Use a distinct SSH key for this service, disable forwarding and interactive use,
and restrict source addresses where operationally possible.

Configure GitHub secret scanning/push protection and a policy requiring action
commit pins. Review Dependabot updates before merging them. Keep the application
service account unprivileged and restrict its database and secret files.

Set APP_ENV=production and HTTPS MONZO_REDIRECT_URI. Production rejects HTTP
requests, placeholder/test secrets, reused signing/encryption keys, and the sample
encryption key. Configure hostname routing at the reverse proxy. API docs/schema
remain available in production. OAuth and refresh do not require a BFF key.

Review deploy/monzo-scheduler.service and deploy/nginx.conf as server templates.
Use DATABASE_URL=sqlite:////var/lib/monzo-scheduler/monzo_scheduler.db so database
writes fit the service sandbox. Keep /srv/monzo-scheduler/.env owner-readable
only (0600) and /var/lib/monzo-scheduler private (0700). Both Alembic and the service
must receive the same keys/environment. The service binds only to loopback,
uses one worker, trusts forwarding headers only from the local proxy, and cannot
write its source tree. The proxy replaces incoming forwarding headers and logs
only method/path/status, omitting query strings and tokens. Review error logging
and external monitoring separately. Restrict firewall ingress to HTTPS and
administrative SSH; never expose port 8000 publicly.

Templates are not applied to the Droplet automatically. Validate nginx -t and
systemd-analyze verify on the host, provision the certificate and hostname, and
review the sandbox paths before installing them. Maintain encrypted backups with
0700 directories/0600 files and keep backup encryption keys separately. Never
back up plaintext historical databases alongside current credentials.
