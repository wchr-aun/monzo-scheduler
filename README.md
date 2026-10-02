# Schedzo

A Python and FastAPI web app for connecting to Monzo and scheduling savings-pot deposits and withdrawals.

After completing the Monzo OAuth flow, send the returned application token as
`Authorization: Bearer <token>` to these endpoints:

- `GET /accounts-with-balances` (optional `account_type` query parameter; each
  account includes `balance_details`, which is `null` when its balance request
  fails)
- `GET /balance?account_id=<account_id>`
- `GET /pots?current_account_id=<account_id>`
- `GET /scheduled-transfers`
- `POST /schedule-transfer`
- `DELETE /schedule-transfer/<setup_id>`
- `POST /logout` to revoke application sessions
- `POST /emergency-stop` to revoke sessions, deactivate schedules, and cancel pending transfers
- `POST /auth/refresh` to rotate an application refresh token

The OAuth callback also returns a `refreshToken`. The frontend BFF should keep
it in its server-side session or a `Secure`, `HttpOnly` cookie and must not
expose it to browser JavaScript. When the 10-minute application JWT expires,
the BFF can call `POST /auth/refresh` with `{"refreshToken":"..."}`. The
response contains a new `token`, a rotated `refreshToken`, `expiresIn`, and
`refreshExpiresIn`. Each successful refresh resets the 60-day inactivity
window. A refresh token can be used only once; BFF refresh requests should be
serialized where possible. If duplicate requests arrive together, the backend
accepts retries of the previous token for 30 seconds and returns the same
rotated refresh token, so the BFF does not lose its session to a race.

Schedule requests use a timezone-aware UK local datetime, a positive amount in
minor currency units, and one of the `daily`, `weekly`, or `monthly` intervals:

```json
{
  "datetime": "2030-01-31T09:15:00Z",
  "interval": "monthly",
  "type": "deposit",
  "amount": 1250,
  "pot_id": "pot_123",
  "account_id": "acc_123"
}
```

Monthly schedules on days 29–31 run on the last valid day of shorter months,
then return to the requested day when it exists again.

Each schedule is stored as an active or deactivated setup. Individual transfer
occurrences are stored separately as pending, completed, failed, or cancelled.
Cancelling a setup cancels its pending occurrence and removes its scheduler job.
An occurrence is marked running while Monzo processes it.

The service resolves the Monzo credentials associated with the token's `sub`
claim and refreshes an expired Monzo access token when possible.

## Security configuration

Set `JWT_SECRET_KEY` to a random value of at least 32 bytes and keep
`JWT_EXPIRATION_SECONDS` between 1 and 3600; the default is 900 seconds. Generate
`TOKEN_ENCRYPTION_KEY` with:

```sh
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

The same encryption key must be available to the application and Alembic before
running `uv run alembic upgrade head`. Migration `0005` encrypts existing Monzo
tokens. Losing the key makes stored tokens unreadable; keep protected backups of
the key and restrict access to the database and its backups. Replace the key only
after re-encrypting stored credentials. Older backups made before migration may
still contain plaintext tokens and should be retired securely; rotate Monzo
credentials if those copies cannot be accounted for.

OAuth state expires after ten minutes. The service limits requests to 120 per
client address per minute and active schedules to 50 per user. These limits and
the scheduler are process-local, so run one worker and configure the ASGI server
to supply the real client address when the service is behind a trusted proxy.
Emergency stop waits for any in-flight transfer, then cancels pending work and
revokes the user's application sessions.

## Logging

Application logs are written to standard error with timestamps, severity, and
the failing endpoint or Monzo operation. Every HTTP response includes an
`X-Request-ID`; failed requests include the same identifier in their log entry
for correlation. Query strings and authentication credentials are omitted so
OAuth codes, JWTs, and Monzo tokens are not written to logs.
