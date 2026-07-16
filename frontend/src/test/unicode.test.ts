import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { text } from "../i18n/strings";

describe("Unicode integrity", () => {
  it("stores Malayalam UI strings as UTF-8 rather than mojibake", () => {
    const source = readFileSync(resolve(process.cwd(), "src/i18n/strings.ts"), "utf8");
    expect(source).toContain("മലയാളം");
    expect(source).toContain("പ്രകാശസംശ്ലേഷണം");
    expect(source).not.toMatch(/Î±â”¤|Î“Ã‡|ï¿½/);
    expect(text.malayalam.malayalam).toBe("മലയാളം");
  });

  it("loads the shared Photosynthesis fixture as UTF-8 JSON", () => {
    const fixture = readFileSync(resolve(process.cwd(), "../shared/fixtures/class-7-photosynthesis.json"), "utf8");
    const parsed = JSON.parse(fixture) as { glossary: Array<{ malayalam_support_label: string }> };
    expect(fixture).toContain("ക്ലോറോഫിൽ");
    expect(parsed.glossary.map((term) => term.malayalam_support_label)).toContain("പ്രകാശസംശ്ലേഷണം");
    expect(fixture).not.toMatch(/Î±â”¤|Î“Ã‡|ï¿½/);
  });
});
