import { useId, useState } from "react";

import type { ApprovedMaterial, StudentGlossaryTerm } from "../api/contracts";
import { Button } from "../components/primitives";

type TrustedTerm = StudentGlossaryTerm;

type TrustedMaterial = Pick<ApprovedMaterial, "id" | "content">;

export type TrustedExplanationAnnotation = {
  before: string;
  term: TrustedTerm;
  after: string;
};

export type OfficialIslExternalResource = Readonly<{
  contextId: string;
  versionNumber: number;
  glossaryTermId: string;
  title: string;
  sourceName: string;
  sourceShortName: string;
  developmentAttribution: string;
  externalUrl: string;
  visibleActionLabel: string;
  accessibleActionLabel: string;
  accessNote: string;
}>;

const DEMO_CONTEXT_V1_ID = "f069db92-d848-5546-b3ad-3b10ee301600";
const DEMO_CHLOROPHYLL_TERM_ID = "a7287dbc-4022-5dbb-9395-1b77c953631c";
const DEMO_TEACHER_EXPLANATION_ID = "166e94f5-7b72-50b0-b137-b9d9844ce88e";

const OFFICIAL_CHLOROPHYLL_ISL_RESOURCE: OfficialIslExternalResource = {
  contextId: DEMO_CONTEXT_V1_ID,
  versionNumber: 1,
  glossaryTermId: DEMO_CHLOROPHYLL_TERM_ID,
  title: "Chlorophyll",
  sourceName: "Indian Sign Language Research and Training Centre",
  sourceShortName: "ISLRTC",
  developmentAttribution: "Developed jointly by CIET, NCERT and ISLRTC.",
  externalUrl: "https://www.youtube.com/watch?v=Oqrmn9kYESk",
  visibleActionLabel: "View official ISLRTC resource",
  accessibleActionLabel: "View official ISLRTC resource for Chlorophyll — opens in a new tab",
  accessNote: "Optional external resource. Internet connection required. Opens in a new tab. It is not created by Shravya and does not replace an interpreter.",
};

const DEMO_EXPLANATION_BEFORE = "Plants use ";
const DEMO_EXPLANATION_AFTER = " to capture sunlight. Water and carbon dioxide are changed into glucose, and oxygen is released.\n\nക്ലോറോഫിൽ സൂര്യപ്രകാശം പിടിച്ചെടുക്കാൻ സഹായിക്കുന്നു. ജലവും കാർബൺ ഡൈ ഓക്സൈഡും ഗ്ലൂക്കോസായി മാറുമ്പോൾ ഓക്സിജൻ പുറത്തുവരുന്നു.";
const DEMO_EXPLANATION_CONTENT = `${DEMO_EXPLANATION_BEFORE}chlorophyll${DEMO_EXPLANATION_AFTER}`;

function isTrustedTerm(term: StudentGlossaryTerm | undefined): boolean {
  return Boolean(
    term
    && term.canonical_term.trim()
    && term.malayalam_support_label?.trim()
    && term.definition.trim(),
  );
}

/**
 * A single, exact allowlist entry. This intentionally accepts only structured
 * approved-context identity; it never falls back to visible term text or prose.
 */
export function resolveOfficialIslExternalResource({
  selectedContextId,
  versionNumber,
  glossaryTermId,
}: {
  selectedContextId: string | null | undefined;
  versionNumber: number | null | undefined;
  glossaryTermId: string | null | undefined;
}): OfficialIslExternalResource | undefined {
  if (
    selectedContextId !== OFFICIAL_CHLOROPHYLL_ISL_RESOURCE.contextId
    || versionNumber !== OFFICIAL_CHLOROPHYLL_ISL_RESOURCE.versionNumber
    || glossaryTermId !== OFFICIAL_CHLOROPHYLL_ISL_RESOURCE.glossaryTermId
  ) {
    return undefined;
  }
  return OFFICIAL_CHLOROPHYLL_ISL_RESOURCE;
}

/**
 * Deliberately narrow: this is a fixture registration, not a text parser.
 * Any copied, altered, or unknown approved context falls back to plain content.
 */
export function resolveTrustedExplanationAnnotation({
  contextId,
  versionNumber,
  material,
  glossaryTerms,
}: {
  contextId: string | null;
  versionNumber: number | null;
  material: TrustedMaterial;
  glossaryTerms: readonly StudentGlossaryTerm[];
}): TrustedExplanationAnnotation | null {
  if (
    contextId !== DEMO_CONTEXT_V1_ID
    || versionNumber !== 1
    || material.id !== DEMO_TEACHER_EXPLANATION_ID
    || material.content !== DEMO_EXPLANATION_CONTENT
  ) {
    return null;
  }

  const matches = glossaryTerms.filter((term) => term.id === DEMO_CHLOROPHYLL_TERM_ID);
  const term = matches.length === 1 ? matches[0] : undefined;
  if (!term || !isTrustedTerm(term) || term.canonical_term !== "Chlorophyll") return null;

  return { before: DEMO_EXPLANATION_BEFORE, term, after: DEMO_EXPLANATION_AFTER };
}

/** Returns a structured, concept-linked student term only; no recovery prose is parsed. */
export function trustedChlorophyllForRecovery(terms: readonly StudentGlossaryTerm[]): TrustedTerm | null {
  const matches = terms.filter((term) => term.canonical_term === "Chlorophyll");
  const term = matches.length === 1 ? matches[0] : undefined;
  return isTrustedTerm(term) ? term ?? null : null;
}

export function TrustedTermDisclosure({
  term,
  resource,
}: {
  term: TrustedTerm;
  resource?: OfficialIslExternalResource;
}) {
  const [expanded, setExpanded] = useState(false);
  const definitionId = useId();
  const action = expanded ? "Hide" : "Show";

  return (
    <span className="trusted-term">
      <Button
        aria-controls={definitionId}
        aria-expanded={expanded}
        aria-label={`${action} teacher-approved meaning for ${term.canonical_term}`}
        className="trusted-term-trigger"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        <span aria-hidden="true" className="trusted-term-cue">Key term</span>
        <span>{term.canonical_term}</span>
        <span aria-hidden="true" className="trusted-term-helper">Tap for meaning</span>
      </Button>
      {expanded ? (
        <span aria-label={`Teacher-approved meaning for ${term.canonical_term}`} className="trusted-term-definition" id={definitionId} role="region">
          <span className="trusted-term-cue">Key term</span>
          <strong className="trusted-term-name" lang="en">{term.canonical_term}</strong>
          <span className="trusted-term-malayalam" lang="ml">{term.malayalam_support_label}</span>
          <span className="trusted-term-copy" lang="en">{term.definition}</span>
          {term.malayalam_explanation ? <span className="trusted-term-copy" lang="ml">{term.malayalam_explanation}</span> : null}
          <span className="trusted-term-status">✓ Teacher-approved term</span>
          {resource ? (
            <span className="official-isl-resource">
              <span className="official-isl-resource-attribution">External educational resource from the {resource.sourceName}.</span>
              <span className="official-isl-resource-development">{resource.developmentAttribution}</span>
              <a
                aria-label={resource.accessibleActionLabel}
                href={resource.externalUrl}
                referrerPolicy="no-referrer"
                rel="noopener noreferrer"
                target="_blank"
              >
                {resource.visibleActionLabel} <span aria-hidden="true">↗</span>
              </a>
              <span className="official-isl-resource-note">{resource.accessNote}</span>
            </span>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
