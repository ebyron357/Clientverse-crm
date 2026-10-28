# AI Software Quality and Security Audit — ebyron357/Clientverse-crm

Status: NOT TESTED. This document is the project-specific audit entrypoint, not an assertion of compliance or quality.

## Canonical governing standard
See [AI Software Quality, Security & Production Readiness Standard](https://github.com/ebyron357/AI-Operating-Standards/blob/main/docs/AI_SOFTWARE_QUALITY_STANDARD.md) (pending approval via [master PR #7](https://github.com/ebyron357/AI-Operating-Standards/pull/7)). The canonical standard covers visual consistency, code debris, fake UI, responsiveness, accessibility, application security, AI-generated defects, data integrity, integrations, autonomous agent governance, performance/SEO/GEO/AEO, customer journeys, HIPAA/government applicability, CI/CD and documentation.

## Required local audit checklist
- [ ] Inventory routes, components, APIs, integrations, deployments, data stores and permissions.
- [ ] Verify branding, design tokens, typography, spacing, gradients, shadows and responsive behavior.
- [ ] Identify dead code, duplicate components, abandoned pages, unused dependencies and conflicting CSS.
- [ ] Verify every button, setting, form, chart, testimonial and displayed metric represents working functionality or is labeled demo.
- [ ] Run accessibility, keyboard, mobile, desktop and browser checks.
- [ ] Verify authentication, authorization, tenant isolation, secrets, upload safety, dependencies and logs.
- [ ] Test database persistence, migrations, data integrity and backups where applicable.
- [ ] Verify integrations, webhooks, automation reliability and error recovery.
- [ ] For agent-enabled systems: inventory agent identity, roles, permissions, supervisor, approvals, traces, stop/revocation and prompt-injection defenses.
- [ ] Validate performance, SEO, GEO, AEO and complete customer workflows.
- [ ] Assess HIPAA, NIST and public-sector contractual requirements only where applicable; document evidence.
- [ ] Run appropriate CI tests and record recovery/rollback steps.
- [ ] Produce defect register with severity P0-P3, reproduction, evidence, remediation owner and acceptance tests.
- [ ] Propose fixes by separate reviewable PR; obtain owner approval before merge/deploy.

## Evidence register
| Check | Result (PASS/FAIL/NOT TESTED/N/A) | Evidence | Finding / action |
| --- | --- | --- | --- |
| Baseline inventory | NOT TESTED | Pending | Inspect repository |
| UI / functionality | NOT TESTED | Pending | Execute real checks |
| Security / data | NOT TESTED | Pending | Verify controls |
| Accessibility / responsive | NOT TESTED | Pending | Test browsers and assistive technology |
| CI / release | NOT TESTED | Pending | Verify workflows |

## Governance
Preserve existing implementations, avoid invented blockers and unsupported claims, report genuine constraints, and retain final owner approval. No production changes are authorized by this checklist alone.
