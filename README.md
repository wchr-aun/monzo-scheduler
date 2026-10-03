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

The OAuth callback also returns a `refreshToken`. When the application JWT
expires (15 minutes by default), the client can call `POST /auth/refresh` with
`{"refreshToken":"..."}`. The response contains a new `token`, a rotated
`refreshToken`, `expiresIn`, and `refreshExpiresIn` (5,184,000 seconds: 60 days
from each successful rotation). Each rotation has a fixed five-second retry window:
concurrent requests using the immediately previous token receive the same token
pair without another rotation. Retries never extend the window. Reuse after the
window or of an older predecessor revokes the session, including its latest JWT.
Serialize frontend refreshes and atomically save replacements to avoid stale
responses overwriting newer tokens. Refresh tokens are stored only as hashes in
SQLite. The bounded retry cache holds token pairs in memory, is scoped to the
application's database/session factory, and is lost on application restart. A
retry after restart or outside the window requires a fresh login. Unknown tokens
receive 401 without revoking unrelated sessions.

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
client address per minute and active schedules to 50 per user. These request limits and
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

Emergency stop persists a scheduling pause across logins. After authenticating
again, explicitly call `POST /resume-transfers` before creating new schedules.
Resuming does not reactivate cancelled schedules. Schedule creation revalidates
the session while holding the same user lock as logout and emergency stop.

Application refresh tokens expire after 60 days without a successful refresh.
Each successful rotation starts another 60-day inactivity window. Ordinary API
requests and duplicate refresh retries do not extend that deadline. There is no
absolute lifetime from the original login and no rotation-count ceiling. Access
JWTs expire according to `JWT_EXPIRATION_SECONDS`. Logout, emergency stop, a new
login, and reuse outside the retry window can invalidate a session. Migration
`0016` backfills inactivity deadlines from the last session update without
restoring revoked sessions or consumed tokens.

OAuth attempts are signed, expire after ten minutes, and must match the browser's
HttpOnly state cookie. Starting a login stores no pending global state. Callback
consumption is persisted to prevent reuse; each client address is limited to five
login starts per ten minutes independently of the general API limit.

Request handling admits at most 64 simultaneous requests, reads at most 16 KiB
per body (including chunked bodies), and allows ten seconds to receive the body.
Excess requests receive 503, oversized bodies 413, and slow bodies 408. Configure
matching or tighter connection/body limits at the production reverse proxy.

Persistent abuse budgets limit each user to 100 schedule creations and 20 app
session issuances per rolling day, plus 60 refresh rotations per rolling hour.
Cancelled schedules still count toward the creation budget. Used-token hashes
have indexed lookups; unknown refresh tokens do not scan session history.
Maintenance runs at startup and hourly, removes sessions revoked for at least a
day and their token hashes, along with expired sessions and OAuth state records. Transfer
history and schedule definitions are retained indefinitely, including completed,
failed, and cancelled transfers and deactivated schedules. Used-token hashes for
live sessions are retained for reuse detection, so they accumulate over the
session lifetime. Protect the database and any exports as financial data.

`POST /emergency-stop` and `POST /disconnect` now also revoke the Monzo connection
at the provider and erase stored tokens after confirmation. They return 204 when
finished or 202 when Monzo is unavailable. A 202 still means local schedules are
paused and all application sessions revoked; the stored connection is blocked.
Revocation is retried every minute, including after process restart. Login is
blocked while revocation remains pending. After confirmed disconnection, reconnect
through OAuth and explicitly resume scheduling. Ordinary logout keeps scheduled
transfers and the Monzo connection intact.

OAuth and refresh retain the direct-client flow without a BFF shared-secret
requirement. Serialize refresh requests per session and persist replacement tokens
atomically. A lost refresh response can be retried within the five-second window
while that rotation is still the latest and the process has not restarted. Clear the frontend session on authentication failure, logout, or
emergency stop. A refresh quota 429 is temporary; retain the current token.

Transfer amounts must be positive signed 64-bit integers. Schedule creation and
explicit resume require a valid application session, without a recent-login
requirement or application-level monetary caps.
