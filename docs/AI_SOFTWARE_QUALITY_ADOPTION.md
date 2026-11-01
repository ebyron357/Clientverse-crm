# AI Software Quality & Security — Project Adoption and Audit

**Repository:** ebyron357/Clientverse-crm

**Canonical governing standard:** [AI Software Quality, Security & Production Readiness — Canonical Standard (Version 1.0)](https://github.com/ebyron357/AI-Operating-Standards/blob/main/docs/AI_SOFTWARE_QUALITY_SECURITY_MASTER_STANDARD.md), approved through [AI-Operating-Standards PR #8](https://github.com/ebyron357/AI-Operating-Standards/pull/8). If this page and the canonical standard disagree, the canonical standard wins.

**Current status: NOT INSPECTED.** Adopting the standard is not proof of an audit, security, accessibility, or compliance.

This page replaces the earlier `AI_SOFTWARE_QUALITY_AUDIT.md`, which pointed to a draft standard that was never approved.

## Execution protocol
- Inventory the real repository architecture, live deployment, roles, data, integrations, and AI agents before claiming findings.
- Record every finding with severity P0-P3, evidence, affected file/line, reproduction, root cause, repair, owner, acceptance tests, and status.
- Do not invent blockers, defects, evidence, or passing checks.
- Preserve working functionality and existing project data.
- Make repairs in isolated branches and reviewable PRs. The owner approves every merge and production release.
- HIPAA, NIST, CMMC, and FedRAMP claims require scope-specific evidence and applicable assessments. Never claim certification without proof.

## Mandatory checklist (verify against the actual implementation)
- [ ] **Inventory:** routes, components, APIs, integrations, deployments, data stores, and permissions.
- [ ] **Visual consistency:** branding, design tokens, typography, spacing, colors, gradients, shadows, and cards.
- [ ] **Code hygiene:** dead code, duplicate components, abandoned pages and routes, unused imports and dependencies, conflicting CSS, and AI-generated debris.
- [ ] **Functional UI:** every button, setting, form, chart, testimonial, and displayed metric works or is clearly labeled demo. No false success messages or production mock data.
- [ ] **Responsive design and accessibility:** mobile navigation, dialogs, tables, tap targets, keyboard use, labels, contrast, and a WCAG 2.2 AA evaluation across browsers.
- [ ] **Security:** authentication, least-privilege server-side authorization, tenant isolation, secret scanning, safe rendering, upload safety, dependencies, and logs.
- [ ] **Backend:** persistence, validation, migrations, data integrity, backups, restore, and observability.
- [ ] **Integrations:** real APIs, OAuth scopes, webhook signatures, retries, automation reliability, and error recovery.
- [ ] **Agent controls (where applicable):** agent identity, roles, tool scope, supervisor, approvals, tracing, stop/revocation, prompt-injection defenses, and owner override.
- [ ] **Performance and discovery:** Core Web Vitals, SEO, GEO, AEO, structured data, and complete customer workflows. No deceptive injection.
- [ ] **Privacy and compliance:** HIPAA, NIST, and public-sector requirements assessed only where they apply, with documented evidence.
- [ ] **Testing and release:** lint, build, unit, E2E, accessibility, visual regression, security, CI, and recorded rollback steps.
- [ ] **Documentation:** architecture, owners, inventory, audit evidence, and the current governing standard.

## Rollout status
- [ ] Baseline inventoried
- [ ] Audit performed with evidence
- [ ] P0/P1 findings addressed
- [ ] Automated and manual tests passed
- [ ] Owner approved release

## Evidence register
| Check | Result (PASS/FAIL/NOT TESTED/N/A) | Evidence | Finding / action |
| --- | --- | --- | --- |
| Baseline inventory | NOT TESTED | Pending | Inspect repository |
| UI / functionality | NOT TESTED | Pending | Execute real checks |
| Security / data | NOT TESTED | Pending | Verify controls |
| Accessibility / responsive | NOT TESTED | Pending | Test browsers and assistive technology |
| CI / release | NOT TESTED | Pending | Verify workflows |

## Governance
This checklist alone authorizes no production changes. The owner keeps final approval over every merge and deployment.
