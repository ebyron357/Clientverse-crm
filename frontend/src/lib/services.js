import { api } from "@/lib/api";

async function get(path, config) {
  const response = await api.get(path, config);
  return response.data;
}

export const commandCenterService = {
  getPortfolio: () => get("/dashboard"),
  getAlerts: (params) => get("/alerts", { params }),
  getIntegrationHealth: () => get("/integrations/health"),
};

export const relationshipService = {
  listCompanies: () => get("/companies"),
  listContacts: () => get("/contacts"),
  listOpportunities: () => get("/opportunities"),
  listWorkspaces: () => get("/workspaces"),
  createCompany: async (input) => (await api.post("/companies", input)).data,
  createContact: async (input) => (await api.post("/contacts", input)).data,
};

export const client360Service = {
  getWorkspace: (workspaceId) => get(`/workspaces/${workspaceId}`),
  updateWorkspace: async (workspaceId, input) => (await api.patch(`/workspaces/${workspaceId}`, input)).data,
};
