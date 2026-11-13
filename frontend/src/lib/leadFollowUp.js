export function leadFollowUp(lead, now = Date.now()) {
  const owner = lead.assigned_name || lead.assigned_to || "Unassigned";
  const taskLink = lead.task_id ? `/tasks?task=${encodeURIComponent(lead.task_id)}` : null;
  const contactLink = lead.contact_id ? `/contacts?contact=${encodeURIComponent(lead.contact_id)}` : null;
  const review = taskLink
    ? { to: taskLink, label: "Review call-back task" }
    : contactLink ? { to: contactLink, label: "Open contact" } : null;

  if (lead.is_test) {
    return { owner, title: "Review test lead", reason: "This is a test submission, not a live follow-up. Check its details and automation history before taking any action.", action: review };
  }
  if (lead.status === "closed" || lead.status === "spam") {
    return { owner, title: "No outreach suggested", reason: lead.status === "closed" ? "This lead is closed. Reopen it only if the conversation should continue." : "This lead is marked as spam. Reopen it only if that was a mistake.", action: null };
  }
  if (lead.status === "responded") {
    return { owner, title: "Review the next follow-up", reason: "Contact has been recorded. Review the conversation and agree on the next step; this does not mean the linked task is still open.", action: review || { to: "/tasks", label: "Review tasks" } };
  }
  if (lead.status !== "new") {
    return { owner, title: "Review lead status", reason: "The lead status is unavailable or unrecognized. Review its history before deciding on outreach.", action: contactLink ? { to: contactLink, label: "Open contact" } : null };
  }

  const hasPhone = typeof lead.phone === "string" && Boolean(lead.phone.trim());
  const hasEmail = typeof lead.email === "string" && Boolean(lead.email.trim());
  const prefersEmail = typeof lead.fields?.preferred_contact === "string" && lead.fields.preferred_contact.trim().toLowerCase() === "email";
  const title = hasEmail && (prefersEmail || !hasPhone) ? "Send a personal email" : hasPhone ? "Call the lead" : "Check contact details";
  const due = lead.sla?.due_at ? new Date(lead.sla.due_at).getTime() : NaN;
  let reason = "No first response has been recorded yet.";
  if (lead.sla?.escalated_at) reason = "The response window passed and this lead was escalated. No first response has been recorded yet.";
  else if (Number.isFinite(due) && due <= now) reason = "The first-response deadline has passed. No first response has been recorded yet.";
  else if (Number.isFinite(due)) reason = "The first-response window is still open. Reach out before the deadline above.";
  if (!hasPhone && !hasEmail) reason += " No phone number or email is on this lead; check the linked record or original submission first.";
  if (!lead.assigned_to && !lead.assigned_name) reason += " No owner is assigned; coordinate who will respond.";
  if (lead.automation?.some((step) => step.result === "failed")) reason += " An automation step failed; review the history below.";

  return { owner, title, reason, action: !hasPhone && !hasEmail && contactLink ? { to: contactLink, label: "Check contact record" } : review };
}
