const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "webapp", "services", "api-client.js"),
  "utf8",
);

async function main() {
  const window = {
    fetch: async () => ({
      ok: false,
      status: 409,
      async json() {
        return {
          ok: false,
          error: { code: "CONFLICT", message: "当前状态冲突。" },
          trace_id: "trace_0123456789abcdef0123456789abcdef",
        };
      },
    }),
  };
  vm.runInNewContext(source, { window, console });
  await assert.rejects(
    async () => window.KOLConnectAPI.get("/api/example"),
    error => {
      assert.equal(error.code, "CONFLICT");
      assert.equal(error.traceId, "trace_0123456789abcdef0123456789abcdef");
      assert.match(error.message, /当前状态冲突/);
      assert.match(error.message, /错误参考：trace_/);
      assert.doesNotMatch(error.message, /secret|token|authorization/i);
      return true;
    },
  );

  window.fetch = async () => ({
    ok: false,
    status: 400,
    async json() { return { error: "LEGACY_ERROR" }; },
  });
  await assert.rejects(
    async () => window.KOLConnectAPI.get("/api/legacy"),
    error => error.message === "LEGACY_ERROR",
  );
  console.log("M7.2 API client compatibility: OK");
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
