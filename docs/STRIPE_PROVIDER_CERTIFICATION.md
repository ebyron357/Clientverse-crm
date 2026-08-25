# ClientVerse CRM — Stripe Test-Mode Certification

**Certification timestamp:** 2026-08-25 EDT
**Current candidate:** `7c0786303b511df3bbd80d14c004a2171e27e3e2`
**CI:** [run 32874240684](https://github.com/ebyron357/Clientverse-crm/actions/runs/32874240684) — **PASS**
**Credential-backed certification result:** **BLOCKED**

> This record distinguishes implemented and deterministic behavior from Stripe sandbox evidence. It does not claim that any Stripe account, key, webhook endpoint, test event, payment, customer, invoice, card, or secret was accessed in this closeout.

## Implemented Lifecycle

The backend recognizes `STRIPE_API_KEY` and `STRIPE_WEBHOOK_SECRET`. The administrative connection check records the provider key mode without returning a key. The certification payment endpoint rejects live-mode credentials, requires a tenant-owned local invoice with a positive amount, creates a test-mode PaymentIntent with tenant and invoice metadata, uses a stable idempotency key, and stores only sanitized payment state.

The webhook endpoint is `POST /api/integrations/stripe/webhook`. It verifies Stripe’s signature against the raw request body before any event handling, writes an idempotency marker through a unique `event_id` index, and only updates an invoice where both the tenant ID and invoice ID match Stripe metadata. Supported payment events are `payment_intent.succeeded`, `payment_intent.payment_failed`, and `payment_intent.canceled`. [1] [2]

## Deterministic Evidence

| Required behavior | Result | Evidence |
|---|---|---|
| Test-mode enforcement | **PASS — code/test scope** | A live-mode key prefix is rejected before any invoice or provider call. |
| Payment success path | **PASS — deterministic scope** | A mocked test PaymentIntent stores a tenant-scoped `succeeded` payment state and a stable idempotency key. |
| Payment failure path | **PASS — deterministic scope** | A mocked provider failure returns a generic HTTP 402 response and records only a bounded provider code. |
| Signed webhook verification | **PASS — deterministic scope** | An invalid Stripe signature returns HTTP 400 before persistence. |
| Webhook success handling | **PASS — deterministic scope** | A signed `payment_intent.succeeded` event updates only the matching tenant invoice. |
| Duplicate webhook behavior | **PASS — deterministic scope** | A second event with the same event ID returns `duplicate: true` and does not repeat the invoice update. |
| Tenant isolation | **PASS — deterministic scope** | Webhook invoice update query includes both `id` and `tenant_id`; payment metadata carries the tenant ID. |
| Secret redaction | **PASS — code/test scope** | Public provider connection responses exclude API keys, webhook secrets, OAuth material, and raw token fields. |
| Retry/failure behavior | **PASS — deterministic scope** | Sync retry and bounded error-state logic are covered by the shared provider lifecycle suite. |
| Stripe sandbox connection | **BLOCKED** | No authenticated Stripe sandbox dashboard or approved test key was available. |
| Real test payment and failure | **BLOCKED** | No Stripe test-mode account or test PaymentMethod was configured. |
| Real webhook delivery and retry | **BLOCKED** | No public production URL, endpoint registration, or webhook signing secret was configured. |
| Disconnect and invalid configured credential | **BLOCKED** | No credential-backed Stripe connection exists to exercise safely. |

The shared deterministic provider suite reports **15 passed**. The full GitHub Actions backend suite reports **137 passed, 4 skipped, 2 warnings** for this candidate. Neither count is substituted for a real Stripe sandbox lifecycle.

## Exact Owner Setup Required

| Order | Owner action | Secure destination | Required result |
|---:|---|---|---|
| 1 | Sign in to Stripe and select a sandbox/test environment. | Stripe Dashboard | Test mode is visibly active. |
| 2 | Create or select a least-privilege server-side test key. | Render secret manager as `STRIPE_API_KEY` | Key is masked in the host; no value is sent in chat or committed. |
| 3 | Deploy and verify the public HTTPS backend URL first. | Render | `GET /api/health` returns a healthy database-backed response. |
| 4 | Register `<PUBLIC_BACKEND_URL>/api/integrations/stripe/webhook` and select `payment_intent.succeeded`, `payment_intent.payment_failed`, and `payment_intent.canceled`. | Stripe Workbench webhook settings | Endpoint is reachable over HTTPS. |
| 5 | Store the endpoint signing secret. | Render secret manager as `STRIPE_WEBHOOK_SECRET` | The `whsec_...` value remains masked and uncommitted. |
| 6 | Run approved sandbox tests with Stripe-provided test PaymentMethods. | Stripe sandbox and deployed CRM | Sanitized evidence for connection, success, decline, signed delivery, duplicate delivery, retry, disconnect, authorization, and tenant isolation. |

## Safety Boundary

Only Stripe sandbox/test credentials and Stripe-provided test objects may be used for this certification. No live credentials, real card details, real-money transaction, key, webhook secret, API response containing sensitive data, or customer data may be stored in this repository or evidence record.

## References

[1]: https://docs.stripe.com/testing — Stripe sandbox and test PaymentMethod guidance.
[2]: https://docs.stripe.com/webhooks — Stripe webhook registration, raw-body verification, and event handling guidance.
[3]: https://docs.stripe.com/webhooks/signature — Stripe webhook signature verification guidance.
