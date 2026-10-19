# Secrets and Access

Never store secret values in GitHub Wiki or repository documentation.

Document only:
- variable name;
- purpose;
- where it is configured;
- who owns rotation;
- what breaks when it is absent;
- how to verify readiness without revealing the value.

Sensitive areas include JWT signing, integration encryption, OAuth client secrets, cron authentication, seeded admin credentials, AI/provider keys, and payment-provider credentials.
