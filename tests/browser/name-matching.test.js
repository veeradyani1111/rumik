import assert from "node:assert/strict";
import test from "node:test";
import { compareIdentity, nameMatchScore } from "../../kyc/kyc-config.js";

test("name matching requires exact normalized names", () => {
  assert.equal(nameMatchScore("Mr. Veer Adyani", "ADYANI, VEER"), 1);
  assert.equal(nameMatchScore("Veer Adyani", "Veer Adyanii"), 0);
  assert.equal(nameMatchScore("", ""), 0);
  assert.equal(nameMatchScore("Mr.", "Dr."), 0);
  assert.equal(compareIdentity({ name: "Veer Adyanii" }, { name: "Veer Adyani" }).name_match, "fail");
  assert.equal(compareIdentity({ name: "Veeradyani" }, { name: "Veer Adyani" }).name_match, "pass");
});
