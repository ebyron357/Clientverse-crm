// What the lead automation did, in plain words. The server records each step as
// `{step, result, detail}` (backend/website_forms.py `LeadPipeline._log`).
const STEP_TEXT = {
  "contact:created": () => "New contact created",
  "contact:matched": () => "Matched to an existing contact",
  "assignment:assigned": (detail) => (detail ? `Assigned to ${detail}` : "Assigned"),
  "assignment:unassigned": () => "Not assigned: every admin was alerted",
  "opportunity:created": () => "Deal created in your pipeline",
  "opportunity:linked": () => "Linked to their open deal",
  "task:created": () => "Call-back task created",
  "automation:failed": () => "Automation stopped early. The lead is still saved in Leads",
};

export function describeLeadStep({ step, result, detail } = {}) {
  const text = STEP_TEXT[`${step}:${result}`];
  return text ? text(detail) : [step, result].filter(Boolean).join(": ");
}
