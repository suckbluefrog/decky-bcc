import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const source = fs.readFileSync(new URL("../src/lib/steamCompat.ts", import.meta.url), "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const module = { exports: {} };
vm.runInNewContext(output, {
  module,
  exports: module.exports,
  window: { setTimeout, clearTimeout, setInterval, clearInterval },
});

const { updateLsfgLaunchOptions } = module.exports;
const wrapper = "/userdata/system/bin/batocera-control-lsfg-launch";
const fex = "/userdata/system/bin/batocera-control-game-launch";
const managed = `${wrapper} --appid 123 %command%`;

assert.equal(updateLsfgLaunchOptions("", "123", true, wrapper), managed);
assert.equal(updateLsfgLaunchOptions(managed, "123", false, wrapper), "");
assert.equal(
  updateLsfgLaunchOptions(`${fex} ${managed} --user-flag`, "123", false, wrapper),
  `${fex} %command% --user-flag`,
);

// FEX may be inserted after LSFG, putting another wrapper between our prefix
// and %command%. Disable/re-enable must still remove stale prefixes and remain
// idempotent rather than nesting another LSFG helper.
const reordered = `${wrapper} --appid 123 ${fex} %command%`;
assert.equal(updateLsfgLaunchOptions(reordered, "123", false, wrapper), `${fex} %command%`);
assert.equal(
  updateLsfgLaunchOptions(reordered, "123", true, wrapper),
  `${fex} ${managed}`,
);
assert.equal(
  updateLsfgLaunchOptions(`${fex} ${managed}`, "123", true, wrapper),
  `${fex} ${managed}`,
);

assert.throws(
  () => updateLsfgLaunchOptions("", "123", true, "/tmp/untrusted-wrapper"),
  /unavailable/,
);

console.log("Launch-option tests passed");
