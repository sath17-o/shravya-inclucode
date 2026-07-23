import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ApprovedMaterial, StudentGlossaryTerm } from "../api/contracts";
import {
  resolveOfficialIslExternalResource,
  resolveTrustedExplanationAnnotation,
  TrustedTermDisclosure,
  trustedChlorophyllForRecovery,
} from "../features/trustedVocabulary";

const contextId = "f069db92-d848-5546-b3ad-3b10ee301600";
const materialId = "166e94f5-7b72-50b0-b137-b9d9844ce88e";
const chlorophyllId = "a7287dbc-4022-5dbb-9395-1b77c953631c";
const material: Pick<ApprovedMaterial, "id" | "content"> = {
  id: materialId,
  content: "Plants use chlorophyll to capture sunlight. Water and carbon dioxide are changed into glucose, and oxygen is released.\n\nക്ലോറോഫിൽ സൂര്യപ്രകാശം പിടിച്ചെടുക്കാൻ സഹായിക്കുന്നു. ജലവും കാർബൺ ഡൈ ഓക്സൈഡും ഗ്ലൂക്കോസായി മാറുമ്പോൾ ഓക്സിജൻ പുറത്തുവരുന്നു.",
};
const chlorophyll: StudentGlossaryTerm = {
  id: chlorophyllId,
  canonical_term: "Chlorophyll",
  malayalam_support_label: "ക്ലോറോഫിൽ",
  definition: "The green pigment that captures light.",
  malayalam_explanation: "ക്ലോറോഫിൽ: വെളിച്ചം പിടിച്ചെടുക്കുന്ന പച്ച വർണകം.",
  sequence: 2,
  concept_ids: ["sunlight-chlorophyll"],
  aliases: [],
};

function resolve(overrides: Partial<{
  contextId: string | null;
  versionNumber: number | null;
  material: Pick<ApprovedMaterial, "id" | "content">;
  glossaryTerms: StudentGlossaryTerm[];
}> = {}) {
  return resolveTrustedExplanationAnnotation({
    contextId,
    versionNumber: 1,
    material,
    glossaryTerms: [chlorophyll],
    ...overrides,
  });
}

describe("trusted vocabulary fixture resolver", () => {
  it("resolves only the exact approved v1 fixture", () => {
    const annotation = resolve();
    expect(annotation).toMatchObject({ before: "Plants use ", after: expect.stringContaining("capture sunlight") });
    expect(annotation?.term).toEqual(expect.objectContaining({ id: chlorophyllId, canonical_term: "Chlorophyll" }));
  });

  it.each([
    ["a wrong context", { contextId: "other-context" }],
    ["a wrong context version", { versionNumber: 2 }],
    ["a wrong material", { material: { ...material, id: "other-material" } }],
    ["changed material content", { material: { ...material, content: `${material.content} Changed.` } }],
    ["a wrong glossary term", { glossaryTerms: [{ ...chlorophyll, id: "other-term" }] }],
    ["an unknown copied context", { contextId: "copied-context" }],
  ])("fails closed for %s", (_label, overrides) => {
    expect(resolve(overrides)).toBeNull();
  });

  it("uses only the structured, current-concept Chlorophyll term for recovery", () => {
    expect(trustedChlorophyllForRecovery([chlorophyll])).toEqual(chlorophyll);
    expect(trustedChlorophyllForRecovery([{ ...chlorophyll, definition: "" }])).toBeNull();
    expect(trustedChlorophyllForRecovery([{ ...chlorophyll, canonical_term: "chlorophil" }])).toBeNull();
    expect(trustedChlorophyllForRecovery([chlorophyll, { ...chlorophyll }])).toBeNull();
  });

  it("resolves the official ISL resource only for the exact context, version, and glossary-term identity", () => {
    const resource = resolveOfficialIslExternalResource({ selectedContextId: contextId, versionNumber: 1, glossaryTermId: chlorophyllId });
    expect(resource).toMatchObject({
      title: "Chlorophyll",
      sourceName: "Indian Sign Language Research and Training Centre",
      externalUrl: "https://www.youtube.com/watch?v=Oqrmn9kYESk",
    });

    const noResource = (overrides: Partial<{ selectedContextId: string | null; versionNumber: number | null; glossaryTermId: string | null }>) => resolveOfficialIslExternalResource({
      selectedContextId: contextId,
      versionNumber: 1,
      glossaryTermId: chlorophyllId,
      ...overrides,
    });
    expect(noResource({ selectedContextId: "wrong-context" })).toBeUndefined();
    expect(noResource({ selectedContextId: "" })).toBeUndefined();
    expect(noResource({ selectedContextId: null })).toBeUndefined();
    expect(noResource({ versionNumber: 2 })).toBeUndefined();
    expect(noResource({ versionNumber: null })).toBeUndefined();
    expect(noResource({ glossaryTermId: "wrong-term" })).toBeUndefined();
    expect(noResource({ glossaryTermId: null })).toBeUndefined();
    expect(noResource({ selectedContextId: "copied-context" })).toBeUndefined();
    expect(noResource({ selectedContextId: "unknown-context" })).toBeUndefined();
    expect(noResource({ glossaryTermId: "another-glossary-term" })).toBeUndefined();
  });

  it("has no text-based or default external-resource fallback", () => {
    const identicalVisibleTermWithWrongId = { ...chlorophyll, id: "different-id" };
    expect(resolveOfficialIslExternalResource({ selectedContextId: contextId, versionNumber: 1, glossaryTermId: identicalVisibleTermWithWrongId.id })).toBeUndefined();
    expect(resolveOfficialIslExternalResource({ selectedContextId: undefined, versionNumber: undefined, glossaryTermId: undefined })).toBeUndefined();
  });
});

describe("TrustedTermDisclosure", () => {
  it("offers a keyboard-operable non-modal definition using student-safe canonical data", async () => {
    const user = userEvent.setup();
    render(<TrustedTermDisclosure term={chlorophyll} />);

    const trigger = screen.getByRole("button", { name: "Show teacher-approved meaning for Chlorophyll" });
    expect(trigger).toHaveTextContent("Key term");
    expect(trigger).toHaveTextContent("Tap for meaning");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Teacher-approved meaning for Chlorophyll" })).not.toBeInTheDocument();

    await user.tab();
    expect(trigger).toHaveFocus();
    await user.keyboard("{Enter}");
    const definition = screen.getByRole("region", { name: "Teacher-approved meaning for Chlorophyll" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(trigger).toHaveAttribute("aria-controls", definition.id);
    expect(definition).toHaveTextContent("Chlorophyll");
    expect(definition).toHaveTextContent("ക്ലോറോഫിൽ");
    expect(definition).toHaveTextContent("The green pigment that captures light.");
    expect(definition).toHaveTextContent("✓ Teacher-approved term");
    expect(definition.querySelector('[lang="ml"]')).toBeInTheDocument();
    expect(definition.querySelector("button")).toBeNull();
    expect(definition.querySelector(".official-isl-resource")).toBeNull();
    expect(document.body.textContent).not.toMatch(/\bchlorophil\b|rejected|unsure|probability|review status/i);

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region", { name: "Teacher-approved meaning for Chlorophyll" })).not.toBeInTheDocument();
    await user.keyboard("[Space]");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(trigger).toHaveFocus();
  });

  it("renders an optional official external resource only inside the expanded trusted definition", async () => {
    const user = userEvent.setup();
    const resource = resolveOfficialIslExternalResource({ selectedContextId: contextId, versionNumber: 1, glossaryTermId: chlorophyllId });
    expect(resource).toBeDefined();
    render(<TrustedTermDisclosure resource={resource} term={chlorophyll} />);

    const trigger = screen.getByRole("button", { name: "Show teacher-approved meaning for Chlorophyll" });
    expect(screen.queryByRole("link", { name: /View official ISLRTC resource for Chlorophyll/ })).not.toBeInTheDocument();
    await user.click(trigger);

    const definition = screen.getByRole("region", { name: "Teacher-approved meaning for Chlorophyll" });
    const link = screen.getByRole("link", { name: "View official ISLRTC resource for Chlorophyll — opens in a new tab" });
    expect(definition).toContainElement(link);
    expect(trigger).not.toContainElement(link);
    expect(link).toHaveTextContent("View official ISLRTC resource");
    expect(link).toHaveTextContent("↗");
    expect(link.querySelector('[aria-hidden="true"]')).toHaveTextContent("↗");
    expect(link).toHaveAttribute("href", "https://www.youtube.com/watch?v=Oqrmn9kYESk");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(link).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
    expect(link).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(link).not.toHaveAttribute("download");
    expect(link).not.toHaveAttribute("ping");
    expect(definition).toHaveTextContent("External educational resource from the Indian Sign Language Research and Training Centre.");
    expect(definition).toHaveTextContent("Developed jointly by CIET, NCERT and ISLRTC.");
    expect(definition).toHaveTextContent("Optional external resource. Internet connection required. Opens in a new tab. It is not created by Shravya and does not replace an interpreter.");
    expect(definition).toHaveTextContent("✓ Teacher-approved term");
    expect(definition).not.toHaveTextContent(/Teacher-approved ISL|Verified ISL sign|Shravya ISL|AI-generated ISL|Generated sign|Interpreter replacement|Complete ISL access|Guaranteed sign|Official Shravya sign/i);
    expect(definition.querySelector("iframe")).toBeNull();
    expect(definition.querySelector("video")).toBeNull();
    expect(definition.querySelector("audio")).toBeNull();
    expect(document.body.querySelector("[autoplay]")).toBeNull();
  });
});
