const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync("webapp/index.html", "utf8");
const settings = fs.readFileSync("webapp/pages/settings.js", "utf8");
const i18n = fs.readFileSync("webapp/i18n.js", "utf8");
const creatorDetail = fs.readFileSync("webapp/pages/creator-library-detail.js", "utf8");

assert.match(html, /id="settings-ai-provider-card"/);
assert.match(html, /id="ai-provider"/);
assert.match(html, /id="ai-api-key"[^>]*type="password"/);
assert.match(html, /id="ai-model"[^>]*list="ai-model-suggestions"/);
assert.match(html, /id="ai-provider-save"/);
assert.match(html, /id="ai-provider-test"/);
assert.match(settings, /await api\.get\("\/api\/settings\/ai-provider"/);
assert.match(settings, /global\.confirm\(t\("settingsAiTestWarning"\)\)/);
assert.match(settings, /api\.post\("\/api\/settings\/ai-provider\/health", \{ remote: true \}/);
assert.doesNotMatch(settings, /loadAiProvider[\s\S]{0,500}ai-provider\/health/);
assert.match(settings, /clear_api_key: app\.checkedOf\("ai-clear-key"\)/);
assert.match(settings, /if \(key\) payload\.api_key = key/);
assert.match(settings, /AI_PROVIDER_AUTHENTICATION_FAILED: "settingsAiAuthFailed"/);
assert.match(settings, /AI_PROVIDER_INVALID_OUTPUT: "settingsAiIncompatibleOutput"/);
assert.match(settings, /AI_PROVIDER_ENDPOINT_KEY_REBIND_REQUIRED: "settingsAiEndpointKeyRebindRequired"/);
assert.match(settings, /if \(button\?\.disabled\) return/);
assert.match(settings, /renderAiResult\(t\("settingsAiSaving"\), "pending"\)/);
assert.match(i18n, /settingsAiTitle: "AI 判断（使用你自己的 API Key）"/);
assert.match(i18n, /settingsAiTestWarning: "测试连接会向当前服务商发送一个最小请求，可能产生少量费用。确认继续吗？"/);
assert.match(i18n, /settingsAiTitle: "AI Decisions \(Use Your Own API Key\)"/);
assert.match(html, /id="creator-ai-decision-generate"/);
assert.match(html, /id="creator-ai-decision-content"[^>]*hidden/);
assert.match(creatorDetail, /api\.post\([\s\S]*\/ai-decision`[\s\S]*\{\}/);
assert.match(creatorDetail, /listen\("creator-ai-decision-generate", "click"/);
assert.match(i18n, /creatorAiDecisionGenerate: "生成 AI 判断"/);
assert.match(i18n, /creatorAiDecisionHint: "仅在你点击后/);

console.log("M9.1-C AI provider settings UI contract passed");
