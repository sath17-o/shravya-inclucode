# Shravya Development Contract

Shravya is a Malayalam-first, child-centred accessibility learning system for Classes 5–10. It is teacher-guided and supports hearing-impaired and neurodivergent learners without inferring disability, behavioural profile, or diagnosis.

## Product architecture

Shravya has four main systems:

1. Access Engine
2. NeuroFlex Engine
3. Revision Intelligence
4. Curriculum Intelligence and Teacher Setup

## Locked demonstration and execution priority

- The vertical slice is the Class 7 Science demonstration lesson, **Photosynthesis in Plants**.
- P0: versioned teacher-approved curriculum context, approved student lesson overview, accessibility, provenance, and reliable offline fixture recovery.
- P1: aliases, ASR misrecognitions, deterministic concept relationships, history, stale-artifact marking, and recoverable errors where required to support P0.
- P2/deferred: broad imports, graph editors, production accounts, collaboration, analytics, and multiple live providers.
- Judge-demo reliability, clear social value, and scope discipline take priority over feature volume.

## Curriculum Intelligence and Teacher Setup

- Teachers prepare course, chapter, lesson, objectives, approved source material, glossary, concepts, and source-labelled questions.
- Curriculum context is versioned: Draft → Needs Review → Approved. Approved versions are immutable; edits create a new draft copy.
- Students can see only the currently approved context.
- Every curriculum-owned record must retain review and source/provenance context appropriate to its scope.
- Never claim formal board alignment without an exact human-approved source; use “Class 7 Science demonstration lesson” otherwise.

## Access Engine

- course setup
- lecture audio upload
- transcription
- glossary-assisted term suggestions
- Confirm / Reject / Unsure
- transcript quality gate
- manual transcript fallback

## NeuroFlex Engine

- support-need selector
- layered notes
- focus journey
- explain differently
- comprehension checkpoints
- learner knowledge state
- next-step revision plan
- My Learning View

## Revision Intelligence

- Question Explorer
- narrow Practice Studio
- saved learning journey
- resume progress

## Safety requirements

- never diagnose neurodivergence
- never create a fixed disability mode
- never infer disability or behavioural traits
- never hide uncertainty
- never generate confident learning content from failed transcript quality
- never use open-web retrieval or an unrestricted chatbot
- never call AI-generated questions exam predictions
- checkpoints must be optional and non-punitive
- learner state must describe concepts, not intelligence
- no API keys in source code
- no fake metrics
- no fabricated expert validation
- quality-gate all downstream generation in later phases
- retain provenance and mark artifacts stale when approved context is superseded
- protect child-centred privacy; production identity and profiling are out of scope

## Accessibility requirements

- keyboard-first operation
- screen-reader labels
- logical heading order
- high contrast
- user-controlled text size and spacing
- no autoplay
- no forced timers
- no flashing content
- visible errors and recovery paths
- pause, resume, undo and skip
- progressive disclosure
- one primary task per screen
- Malayalam-first localization with correct `lang="ml"` and `lang="en"` spans in bilingual output

## Engineering rules

- plan before implementation
- build one module at a time
- use typed input/output contracts
- add tests for every deterministic module
- mock all paid API calls in tests
- explain every changed file
- run tests before completing a task
- do not add features outside the approved scope
- keep frontend and backend separated
- preserve offline demo fallbacks
- do not add features outside the approved phase or P0/P1 scope

## Later flagship modules

- Visual Story and Read Along are mandatory later flagship modules, not Phase 2 work.
- Focus Journey, Explain Differently, checkpoints, adaptive learner state, Question Explorer matching, and Practice Studio remain later-phase behaviour.
