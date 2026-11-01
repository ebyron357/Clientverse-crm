# AI Software Quality & Security — Project Adoption and Audit

**Repository:** `ebyron357/Clientverse-crm`
**Adopted baseline:** canonical Version 1.0.
**Current CRM audit status: NOT INSPECTED.** Adoption and documentation validation do not prove completed application testing, security, accessibility, compliance, deployment, or production readiness.

## Document authority and source control

- **Canonical governing standard:** [current master standard](https://github.com/ebyron357/AI-Operating-Standards/blob/main/docs/AI_SOFTWARE_QUALITY_SECURITY_MASTER_STANDARD.md).
- **Approved Version 1.0 snapshot:** [standard at approval merge commit `38c37c673b932df158d113fd8f47c269adbf6964`](https://github.com/ebyron357/AI-Operating-Standards/blob/38c37c673b932df158d113fd8f47c269adbf6964/docs/AI_SOFTWARE_QUALITY_SECURITY_MASTER_STANDARD.md), introduced by [merged approval PR #8](https://github.com/ebyron357/AI-Operating-Standards/pull/8). Git blob: `d60123e9524adc7af51e1e84d1baee69c5efe3d5`.
- Authenticated reads on 2026-11-01 found the approved snapshot and current `main` file identical. A reader's 404 is not by itself evidence that the canonical reference is broken; record the path, ref, reader/access context, and result. If the source cannot be retrieved, mark source verification BLOCKED rather than inventing approval or removing controls.
- The canonical standard governs quality, security, inspection, and release requirements. This page reproduces its complete Version 1.0 body below without abridging its 14 categories or acceptance rules. If this page disagrees with the approved canonical standard, the canonical standard governs; reconcile this complete adoption document against the approved source before using a newer revision.
- The [CRM governing document](CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md) remains the authority for product scope, architecture, capability status, and implementation order. Its compatible, stricter repository controls remain in force. The [owner/admin manual](CLIENTVERSE_CRM_OWNER_ADMIN_MANUAL.md) remains the owner-procedure source of truth. This consolidation changes none of those documents, product records, interfaces, data, deployments, or integrations.
- [PR #55](https://github.com/ebyron357/Clientverse-crm/pull/55) consolidates the earlier adoption and audit pages into this complete replacement and proposes deletion of `AI_SOFTWARE_QUALITY_AUDIT.md`. The deleted page pointed to closed, unmerged draft PR #7 and an obsolete path. It contained only pending audit rows, not verified test results. Deletion takes effect on the default branch only after owner approval and merge; its prior content remains in Git history.
- When an approved requirement changes, update this entire document, preserve applicable controls, remove duplication, and retire superseded guidance only after approved consolidation. Do not create competing instruction fragments.

## CRM execution and independent QA

- Inventory the actual branch/commit, architecture, live deployment, routes, components, APIs, integrations, data stores, roles, permissions, and AI agents before claiming findings. Preserve the existing implementation; this is not authority to redesign or migrate the CRM.
- Repairs belong in isolated branches and reviewable PRs. The owner retains approval over every merge and deployment; this document grants neither.
- Apply [CRM governing document §12](CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md#12-status-control-and-evidence-rules): execution and inspection are separate functions, and independent QC may reject a completion claim. An implementer's checklist, this review, a bot's success label, or historical CI is not a substitute for the required independent QA/security evidence.
- Preserve the mandatory [Jev QC verification gate in AGENTS.md](../AGENTS.md#jev-qc-verification-gate-mandatory-before-claiming-completion), using [the existing submitter](../scripts/jev_qc.mjs) and the production n8n central gate. Only an explicit `qc_status: VERIFIED_COMPLETE` permits a verified-complete task claim; retain `n8n_execution_id` verbatim. Missing configuration, an unavailable service, malformed output, or any other verdict fails closed. Do not call TypeSafe directly, create a substitute gate, expose webhook capabilities/tokens, or reuse an unrelated task's verdict.
- Preserve [CRM governing document §6](CLIENTVERSE_CRM_CANONICAL_GOVERNING_DOCUMENT.md#6-mandatory-external-component-security-architecture): external skills, MCP tools/servers, plugins, and agent packages require both NVIDIA and applicable Cisco security layers, version/digest-bound evidence and reviewer decisions, then tenant allowlisting and approval. A checklist or unconfigured scanner is not evidence that either gate ran.
- Keep the canonical independent security review, manual keyboard/screen-reader checks, and agent red-team tests as distinct obligations. Mark an inapplicable control NOT APPLICABLE only with a documented scope-based reason; an unbuilt or unverified control is not automatically inapplicable.
- A "demo" label never waives the prohibition on fabricated testimonials, metrics, integrations, customer logos, false successes, production mock data, or disguised placeholders. Controlled test fixtures used for verification do not authorize persistent test/demo/smoke records in customer-production tenants (CRM governing document §1.4).
- The canonical P1 risk-acceptance provision does not automatically waive stricter CRM program closeout requirements: §13 of the CRM governing document requires no P0/P1 blocker remaining. Record any real conflict and obtain an explicit owner decision within legal and technical limits; never silently lower a gate.

## Canonical Version 1.0 requirements

The following body is reproduced from the pinned approved source above. Checkmarks remain unset because this document does not perform the CRM audit.

## Non-negotiable operating rules
- Preserve working functionality, user data, project identity, established branding, and existing integrations. Do not rebuild or redesign without approval.
- Inspect before changing. Never invent defects, blockers, audit evidence, compliance status, tests, or completion.
- Owner is final authority. Agents may execute authorized reversible work; require explicit approval for destructive, financial, external-publication, sensitive-data, privilege, or production-impacting actions.
- Security/legal/technical constraints are reported accurately, not bypassed. Continue independent authorized work.
- Every issue has reproducible evidence, severity, affected path, proposed repair, owner, acceptance test, and status.
- Maintain this as a complete canonical document. Superseded instructions must not silently override it.

## Universal inspection checklist
Use [ ] unverified, [x] verified with evidence, N/A with reason, and BLOCKED with precise external dependency.

### 1. Visual and design integrity
- [ ] Consistent typography, spacing, grid, breakpoints, colors, radii, borders, shadows, icons, states, and brand tokens.
- [ ] No random gradients/glows, generic AI cards, inconsistent layouts, excessive rounded corners, stock AI branding, or decorative artifacts.
- [ ] All views visually reviewed against approved reference; screenshots and visual regression tests captured.

### 2. Code hygiene and architecture
- [ ] Remove verified unused imports, dependencies, files, components, duplicate logic, abandoned routes, dead CSS, obsolete comments.
- [ ] No hallucinated packages/APIs, hardcoded secrets/config, conflicting patterns, broken imports, circular dependencies, unsafe casts.
- [ ] Preserve existing behavior through tests; maintain shared components, typed boundaries, documented architecture.

### 3. Genuine functional UI
- [ ] Every button, link, form, filter, search, setting, chart, export, notification, and CTA performs a verified real action.
- [ ] No fabricated testimonials, live metrics, integrations, customer logos, fake successes, production mock data, or disguised placeholders.
- [ ] Verify loading, empty, error, offline, permissions, retry, and success states against backend results.

### 4. Responsive and cross-browser
- [ ] Test phone/tablet/desktop, zoom, orientation, touch/keyboard, Safari/Chrome/Firefox/Edge.
- [ ] No overflow, clipped dialogs, inaccessible menus, tiny targets, hidden actions, keyboard-overlay defects.

### 5. Accessibility
- [ ] Evaluate WCAG 2.2 AA: contrast, labels, semantic headings, landmarks, focus, keyboard, dialogs, errors, alt text, reduced motion.
- [ ] Manual screen-reader and keyboard tests supplement automated accessibility scans.

### 6. Application security
- [ ] Scan source, git history, CI logs, and builds for secrets; revoke/rotate exposed credentials.
- [ ] Enforce server-side authentication, authorization, object-level permissions, tenant isolation, least privilege, and MFA where required.
- [ ] Validate inputs and outputs; prevent XSS, injection, SSRF, unsafe HTML, CSRF as applicable; secure sessions and CORS.
- [ ] Protect uploads, storage, downloads, webhooks, backups, logs, rate limits, dependencies, and supply chain.
- [ ] Document threats, tests, findings, remediations, and independent security review.

### 7. Backend and data integrity
- [ ] Validate schemas, migrations, transactions, concurrency, idempotency, constraints, retention, exports, restore tests.
- [ ] Verify real persistence, row-level controls, tenant boundaries, auditability, encryption in transit and at rest.

### 8. Integrations and automation
- [ ] Inventory APIs, scopes, connectors, credentials, quotas, retries, timeouts, signatures, replay protection, failure queues.
- [ ] Verify actual end-to-end workflows, handoffs, notifications, recovery, and observability.

### 9. AI agent and workforce governance
- [ ] Register every agent with immutable ID, category, role, owner, supervisor, allowed tools, permissions, lifecycle and training/onboarding evidence.
- [ ] Enforce bounded autonomy, explicit approval gates, credential isolation, prompt-injection defense, delegation restrictions, tool allowlists, cost/runtime limits, and immediate revocation/kill switch.
- [ ] Trace every agent action, API call, browser action, task, handoff, approval, error, outcome, time and cost; secure sensitive traces.
- [ ] Verify JEV automation, daily timesheets, agent registry, workforce reporting, incident response and owner override.
- [ ] Red-team rogue behavior, unauthorized actions, exfiltration, cross-agent escalation, infinite loops, and misleading completion claims.

### 10. Performance, SEO, GEO and AEO
- [ ] Measure Core Web Vitals, bundles, caching, API latency, hydration, image loading and resource usage.
- [ ] Validate metadata, canonical tags, crawl/index rules, sitemaps, structured data, accessible semantic content, link integrity.
- [ ] No deceptive SEO injection, fabricated citations, fake reviews, hidden content, or unsupported ranking promises.

### 11. Business and user journeys
- [ ] Verify onboarding, authentication, account recovery, CRM leads, checkout/billing, support, consent, communications, analytics, admin workflows.
- [ ] Check actual conversion events and complete customer journeys by role.

### 12. Privacy and regulatory readiness
- [ ] Inventory data classes, processors, data flows, access, retention, consent, deletion, incidents and audit evidence.
- [ ] For HIPAA-scoped workflows: complete risk analysis, required safeguards, access/audit controls, contingency and incident plans, workforce training, and BAAs as applicable before ePHI processing.
- [ ] Map relevant NIST controls and government obligations to actual contracts/data (e.g., NIST 800-53, 800-171, CMMC, FedRAMP only when applicable); never claim certification/authorization without evidence.
- [ ] Record gaps, control owners, implementation proof, test results and external assessments as required.

### 13. Testing, deployment and recovery
- [ ] Passing lint, types, build, unit, integration, end-to-end, security, accessibility, and visual regression checks.
- [ ] CI branch protection, reviewed PRs, staging validation, secret management, deployment smoke tests, monitoring, rollback and disaster recovery.
- [ ] No merge or production release based on invented passing checks.

### 14. Documentation and maintenance
- [ ] Keep architecture, dependency map, runbooks, incident response, owners, API inventory, registries, changelog, evidence and current source of truth.
- [ ] Remove contradictory and superseded documents only after approved consolidation.

## Defect priority
P0: active exposure, unauthorized access, serious data loss — contain immediately.
P1: broken critical workflow, tenant isolation, high-risk agent authorization — remediate before affected release.
P2: material accessibility, responsive, performance, functional degradation — scheduled verified repair.
P3: cosmetic inconsistencies and harmless debris — controlled cleanup.

## Required audit record
Repository | commit SHA | environment | inspected scope | issue ID | severity | evidence (file/line, screenshot, logs) | reproduction | impact | root cause | proposed change | tests | owner | approval | status | verification date.
Status vocabulary: NOT INSPECTED / VERIFIED PASS / VERIFIED FAIL / NOT APPLICABLE / BLOCKED (with exact cause). Never equate missing evidence with pass.

## Repair workflow
1. Inventory project and verify actual branch/deployment, baseline, ownership, dependencies.
2. Capture evidence, risk and tests before edits; rank P0-P3.
3. Make smallest safe correction in an isolated branch; preserve public interfaces and data.
4. Run automated and manual checks, negative/security tests and visual comparison.
5. Open reviewable PR with before/after evidence, rollback plan, remaining risks and explicit acceptance criteria.
6. Obtain owner approval for release; verify post-deployment behavior; log outcomes.
7. Maintain full canonical replacement when this standard changes.

## Release acceptance
No unresolved P0; P1 must be resolved or explicitly risk-accepted by authorized owner only where legally and technically permissible. Critical workflows verified with real data or controlled test fixtures, security boundaries tested, accessibility and responsive checks evidenced, CI results linked, rollback available, and owner release decision recorded. No blanket claim of HIPAA, NIST, CMMC, FedRAMP, or WCAG compliance without scoped evidence and required independent validation.

## Suggested verification tools (adopt only if suitable)
Playwright, Vitest/Jest, Testing Library, axe-core, Lighthouse, Storybook/Chromatic, ESLint, TypeScript, Knip, depcheck, Semgrep, CodeQL, Gitleaks, Trivy, OWASP ZAP, Dependabot/Renovate, Sentry, OpenTelemetry. Verify licenses, configuration, suitability and real findings; tools do not replace human review.

## CRM rollout status

- [ ] Baseline inventoried at a recorded commit and environment.
- [ ] All 14 categories inspected, with evidence and justified applicability.
- [ ] Findings recorded and P0/P1 disposition documented under the governing acceptance rules.
- [ ] Required automated and manual tests passed with linked evidence.
- [ ] Independent QA/security review and task-specific Jev QC result recorded.
- [ ] Owner merge decision and production-release decision separately recorded.
- [ ] Approved deployment verified and recovery evidence recorded.

## CRM evidence register

Use the canonical audit vocabulary: NOT INSPECTED / VERIFIED PASS / VERIFIED FAIL / NOT APPLICABLE / BLOCKED (with exact cause). An unchecked box means unverified; N/A requires a reason. No previous `NOT TESTED` row has been converted into a passing result.

This is an audit-coverage index. Create a full required audit record for each inspected control and each finding, with every field defined above: repository, commit SHA, environment, inspected scope, issue ID, severity, evidence, reproduction, impact, root cause, proposed change, tests, owner, approval, status, and verification date. Link those records from this index. Evidence must identify the exact revision and environment tested; missing evidence never means pass.

| Scope | Status | Evidence / required next verification |
| --- | --- | --- |
| Baseline inventory | NOT INSPECTED | Record actual repository, deployment, data, roles, integrations, and agents. |
| 1. Visual and design integrity | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 2. Code hygiene and architecture | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 3. Genuine functional UI | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 4. Responsive and cross-browser | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 5. Accessibility | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 6. Application security | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 7. Backend and data integrity | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 8. Integrations and automation | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 9. AI agent and workforce governance | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 10. Performance, SEO, GEO and AEO | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 11. Business and user journeys | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 12. Privacy and regulatory readiness | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 13. Testing, deployment and recovery | NOT INSPECTED | Pending scoped inspection and full audit record. |
| 14. Documentation and maintenance | NOT INSPECTED | Pending scoped inspection and full audit record. |


Documentation-only validation evidence is recorded in [the PR #55 review record](evidence/ai-quality-pr55-validation-20261101.md). That record assesses these documents; it does not change the CRM audit results above.

## Governance and release decision

Adoption alone authorizes no production change. The owner retains final approval for every merge and deployment. Preserve the canonical release-acceptance requirements, independent QA/security validation, the task-specific Jev completion gate, and the CRM program's definition of done. Record actual approvals and verification results before changing status; neither this page nor a merged documentation PR is a compliance certificate.
