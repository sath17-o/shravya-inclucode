# Shravya Development Contract

Shravya is a Malayalam-first accessibility learning system for hearing-impaired and neurodivergent learners.

## Product architecture

Shravya has three main systems:

1. Access Engine
2. NeuroFlex Engine
3. Revision Intelligence

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

- PYQ Radar
- Practice Studio
- saved learning journey
- resume progress

## Safety requirements

- never diagnose neurodivergence
- never create a fixed disability mode
- never hide uncertainty
- never generate confident learning content from failed transcript quality
- never call AI-generated questions exam predictions
- checkpoints must be optional and non-punitive
- learner state must describe concepts, not intelligence
- no API keys in source code
- no fake metrics
- no fabricated expert validation

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