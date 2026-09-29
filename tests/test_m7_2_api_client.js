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
    KOLConnectI18n: {
      t(key, params) {
        const messages = {
          apiServerUnreachable: "Cannot connect to KOLConnect.",
          apiServerError: "The service could not process this request.",
          apiInvalidResponse: "The service returned an unrecognized response.",
          apiErrorReference: `Error reference: ${params?.trace_id || ""}`,
          mailGmailAuthRejected: "Gmail rejected the current credentials.",
        };
        return messages[key] || `[missing:${key}]`;
      },
    },
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
      assert.match(error.message, /(?:错误参考|Error reference): trace_/);
      assert.doesNotMatch(error.message, /secret|token|authorization/i);
      return true;
    },
  );

  window.fetch = async () => ({
    ok: false,
    status: 400,
    async json() {
      return {
        ok: false,
        error: { code: "GMAIL_AUTH_REJECTED", message: "raw provider details must not render" },
      };
    },
  });
  await assert.rejects(
    async () => window.KOLConnectAPI.post("/api/mail/test", {}),
    error => {
      assert.equal(error.code, "GMAIL_AUTH_REJECTED");
      assert.equal(error.kind, "domain");
      assert.equal(error.message, "Gmail rejected the current credentials.");
      return true;
    },
  );

  window.fetch = async () => {
    throw new TypeError("network down");
  };
  await assert.rejects(
    async () => window.KOLConnectAPI.get("/api/unreachable"),
    error => {
      assert.equal(error.code, "SERVER_UNREACHABLE");
      assert.equal(error.kind, "connection");
      assert.equal(error.message, "Cannot connect to KOLConnect.");
      return true;
    },
  );

  window.fetch = async () => ({
    ok: false,
    status: 500,
    async json() {
      return {
        ok: false,
        error: { code: "INTERNAL_SERVER_ERROR", message: "internal details must not render" },
        trace_id: "trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      };
    },
  });
  await assert.rejects(
    async () => window.KOLConnectAPI.get("/api/failure"),
    error => {
      assert.equal(error.kind, "server");
      assert.equal(error.code, "INTERNAL_SERVER_ERROR");
      assert.match(error.message, /The service could not process/);
      assert.match(error.message, /Error reference: trace_aaaaaaaa/);
      assert.doesNotMatch(error.message, /internal details/);
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
