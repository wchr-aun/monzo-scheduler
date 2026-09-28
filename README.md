# Monzo Scheduler

A Python and FastAPI web app for connecting to Monzo and scheduling savings-pot deposits and withdrawals. The project is in development; scheduled transfers are not implemented yet.

After completing the Monzo OAuth flow, send the returned application token as
`Authorization: Bearer <token>` to these endpoints:

- `GET /accounts-with-balances` (optional `account_type` query parameter; each
  account includes `balance_details`, which is `null` when its balance request
  fails)
- `GET /balance?account_id=<account_id>`
- `GET /pots?current_account_id=<account_id>`

The service resolves the Monzo credentials associated with the token's `sub`
claim and refreshes an expired Monzo access token when possible.

## Logging

Application logs are written to standard error with timestamps, severity, and
the failing endpoint or Monzo operation. Every HTTP response includes an
`X-Request-ID`; failed requests include the same identifier in their log entry
for correlation. Query strings and authentication credentials are omitted so
OAuth codes, JWTs, and Monzo tokens are not written to logs.
