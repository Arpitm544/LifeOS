import assert from "node:assert/strict";
import test from "node:test";
import { workspaceStorageKey } from "../src/lib/workspace-storage.ts";

test("workspace data uses distinct keys for each authenticated user", () => {
  assert.notEqual(workspaceStorageKey("user_one"), workspaceStorageKey("user_two"));
  assert.notEqual(workspaceStorageKey("user_one"), "lifeos.workspace.v1");
  assert.equal(workspaceStorageKey("user_one"), workspaceStorageKey("user_one"));
});

test("anonymous identities cannot access a workspace storage key", () => {
  assert.throws(() => workspaceStorageKey(""));
  assert.throws(() => workspaceStorageKey("   "));
});
