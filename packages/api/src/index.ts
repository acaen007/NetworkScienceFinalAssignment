/**
 * Minimal API client for the ManyWorlds project.
 *
 * This client uses the Fetch API to make requests to your Next.js Route
 * Handlers or FastAPI services.  Replace these functions with a
 * generated OpenAPI client or tRPC hooks once your backend contracts
 * stabilize.
 */
export async function getPerson(id: string) {
  const response = await fetch(`/api/people/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch person ${id}`);
  }
  return response.json();
}

export async function listViews() {
  const response = await fetch('/api/views');
  if (!response.ok) {
    throw new Error('Failed to fetch views');
  }
  return response.json();
}