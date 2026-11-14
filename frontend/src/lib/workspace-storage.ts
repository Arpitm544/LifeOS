export function workspaceStorageKey(userId: string) {
  if (!userId.trim()) throw new Error("An authenticated user is required for workspace storage.");
  return `lifeos.workspace.v1:${userId}`;
}
