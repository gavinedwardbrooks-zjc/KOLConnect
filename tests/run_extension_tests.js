"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");

function walk(directory, predicate) {
  const matches = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      matches.push(...walk(fullPath, predicate));
    } else if (predicate(entry.name)) {
      matches.push(fullPath);
    }
  }
  return matches.sort((left, right) => left.localeCompare(right, "en"));
}

function runNode(args, label) {
  const result = spawnSync(process.execPath, args, {
    cwd: ROOT,
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${label} failed with exit code ${result.status}`);
  }
}

function runExtensionTests() {
  const tests = walk(__dirname, (name) => /^test_.*\.(js|mjs)$/.test(name));
  if (tests.length === 0) {
    throw new Error("No extension tests were discovered");
  }
  for (const testFile of tests) {
    runNode([testFile], path.relative(ROOT, testFile));
  }
  console.log(`Extension tests passed: ${tests.length} files`);
}

function checkExtensionSyntax() {
  const extensionRoot = path.join(ROOT, "chrome_extension");
  const sources = walk(extensionRoot, (name) => /\.(js|mjs)$/.test(name));
  if (sources.length === 0) {
    throw new Error("No extension JavaScript files were discovered");
  }
  for (const sourceFile of sources) {
    runNode(["--check", sourceFile], path.relative(ROOT, sourceFile));
  }
  console.log(`Extension syntax passed: ${sources.length} files`);
}

if (process.argv.includes("--syntax")) {
  checkExtensionSyntax();
} else {
  runExtensionTests();
}
