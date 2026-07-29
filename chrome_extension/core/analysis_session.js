(() => {
  class AnalysisSessionController {
    constructor(timeoutMs = 10000) {
      this.timeoutMs = timeoutMs;
      this.sequence = 0;
      this.currentSessionId = "";
    }

    begin() {
      this.sequence += 1;
      this.currentSessionId = `${Date.now()}-${this.sequence}`;
      return this.currentSessionId;
    }

    isCurrent(sessionId) {
      return Boolean(sessionId) && sessionId === this.currentSessionId;
    }

    invalidate() {
      return this.begin();
    }

    async waitFor(promise, sessionId) {
      let timeoutId;
      try {
        return await Promise.race([
          promise,
          new Promise((_, reject) => {
            timeoutId = setTimeout(() => {
              const error = new Error("ANALYSIS_TIMEOUT");
              error.name = "AnalysisTimeoutError";
              reject(error);
            }, this.timeoutMs);
          })
        ]);
      } finally {
        clearTimeout(timeoutId);
      }
    }
  }

  globalThis.KOLConnectAnalysisSessionController = AnalysisSessionController;
})();
