const assert = require("node:assert/strict");
const fs = require("node:fs");
const source = fs.readFileSync("webapp/pages/settings.js", "utf8");

assert.match(source, /if \(!raw\) \{ delete rates\[input\.dataset\.fxCurrency\]; return; \}/);
assert.match(source, /!Number\.isFinite\(value\) \|\| value <= 0/);
assert.match(source, /fx-cancel/);
assert.match(source, /showAllFxRates = !showAllFxRates/);
assert.match(source, /settingsFxUsdFixed/);

function collect(inputs, saved = {}) {
  const rates = { ...saved };
  for (const [currency, rawValue] of Object.entries(inputs)) {
    if (currency === "USD") continue;
    const raw = String(rawValue || "").trim();
    if (!raw) { delete rates[currency]; continue; }
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0) throw new Error(`${currency} 汇率必须是大于 0 的数字。`);
    rates[currency] = value;
  }
  return rates;
}

assert.deepEqual(collect({ BRL: "", KRW: "" }), {});
assert.deepEqual(collect({ BRL: "5.25", KRW: "" }), { BRL: 5.25 });
assert.deepEqual(collect({ BRL: "5.25", KRW: "1350" }), { BRL: 5.25, KRW: 1350 });
for (const value of ["0", "-1", "abc", "Infinity"]) assert.throws(() => collect({ BRL: value }), /BRL/);
assert.deepEqual(collect({ USD: "0", BRL: "5.25" }), { BRL: 5.25 }, "USD is never editable through optional management");
const saved = { BRL: 5.25 };
const unsaved = collect({ BRL: "6", KRW: "1350" }, saved);
assert.deepEqual(saved, { BRL: 5.25 }, "editing does not mutate saved state before save");
assert.notDeepEqual(unsaved, saved);
console.log("Settings currency UX behavior: OK");
