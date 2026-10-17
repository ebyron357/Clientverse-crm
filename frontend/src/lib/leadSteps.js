// What the lead automation did, as sentences. The server records each step as
// `{step, result, detail}` (backend/website_forms.py `LeadPipeline._log`); its details
// are record ids and addresses, which mean nothing to the person reading the lead, so
// only the step's meaning is shown.
const SENTENCES = {
  "contact:created": () => "Added them as a new contact",
  "contact:matched": () => "Matched them to a contact you already had",
  "assignment:assigned": (assignee) => `Assigned the lead to ${assignee || "an agent"}`,
  "assignment:unassigned": () => "No agent is set up for this form, so every admin was alerted",
  "opportunity:created": () => "Opened a deal",
  "opportunity:linked": () => "Added it to their open deal",
  "task:created": () => "Created a call-back task",
  "automation:failed": () => "Something went wrong after the lead was saved. The lead is safe here; check the contact and deal by hand.",
};

export function describeLeadStep(step = {}, { assignee } = {}) {
  const sentence = SENTENCES[`${step.step}:${step.result}`];
  if (sentence) return sentence(assignee || (step.step === "assignment" ? step.detail : ""));
  return `${step.step} · ${step.result}`.replace(/_/g, " ");
}
