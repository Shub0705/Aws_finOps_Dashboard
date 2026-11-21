const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function getResourceActivities(accountId) {
  const params = new URLSearchParams();

  if (accountId && accountId !== "all") {
    params.set("account_id", accountId);
  }

  const query = params.toString();

  const response = await fetch(
    `${API_BASE}/api/resource-tracking/resources${query ? `?${query}` : ""}`
  );

  if (!response.ok) {
    throw new Error(`Resource Tracking API error: ${response.status}`);
  }

  return response.json();
}
