# Monzo Scheduler

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

The service resolves the Monzo credentials associated with the token's `sub`
claim and refreshes an expired Monzo access token when possible.

## Logging

Application logs are written to standard error with timestamps, severity, and
the failing endpoint or Monzo operation. Every HTTP response includes an
`X-Request-ID`; failed requests include the same identifier in their log entry
for correlation. Query strings and authentication credentials are omitted so
OAuth codes, JWTs, and Monzo tokens are not written to logs.
