import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

// Where a person stands with the business. The server holds the same list
// (crm_core.LIFECYCLE_STAGES) and refuses anything else.
export const LIFECYCLE = [
  { value: "lead", label: "Lead", tone: "info" },
  { value: "qualified", label: "Qualified", tone: "brand" },
  { value: "customer", label: "Customer", tone: "success" },
  { value: "former_customer", label: "Former customer", tone: "warning" },
  { value: "partner", label: "Partner", tone: "violet" },
  { value: "other", label: "Other", tone: "neutral" },
];
export const lifecycleOf = (value) => LIFECYCLE.find((stage) => stage.value === value);

export const FIELD_TYPES = [
  { value: "text", label: "Short text" },
  { value: "long_text", label: "Long text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "select", label: "Choice" },
  { value: "checkbox", label: "Yes / no" },
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "url", label: "Web address" },
];
export const fieldTypeLabel = (type) => FIELD_TYPES.find((item) => item.value === type)?.label || type;

export const RECORD_OBJECTS = [
  { value: "contacts", label: "Contacts", path: "/contacts" },
  { value: "companies", label: "Companies", path: "/companies" },
  { value: "deals", label: "Deals", path: "/opportunities" },
];

/** The live field definitions for one record type, and a way to reload them. */
export function useFieldDefs(object, { includeArchived = false } = {}) {
  const [defs, setDefs] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const reload = useCallback(async () => {
    try {
      const { data } = await api.get("/custom-fields", { params: { object, include_archived: includeArchived } });
      setDefs(data.items || []);
    } catch { setDefs([]); }
    finally { setLoaded(true); }
  }, [object, includeArchived]);
  useEffect(() => { reload(); }, [reload]);
  return { defs, loaded, reload };
}

/** A stored value as a person reads it. Empty values read as null so callers can say "Not set". */
export function formatFieldValue(def, value) {
  if (value === null || value === undefined || value === "") return null;
  if (def.type === "checkbox") return value ? "Yes" : "No";
  if (def.type === "number") return Number(value).toLocaleString();
  if (def.type === "date") {
    const date = new Date(`${value}T00:00:00`);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
  return String(value);
}
