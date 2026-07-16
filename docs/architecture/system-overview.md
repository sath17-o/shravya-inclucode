# System overview

Shravya has three product systems:

1. **Access Engine**: approved course context, audio, transcript, glossary recovery, and the quality gate.
2. **NeuroFlex Engine**: learner-selected presentation support, layered learning, Focus Journey, explanations, Visual Story, Read Along, checkpoints, concept states, and next steps.
3. **Revision Intelligence**: Question Explorer, narrow Practice Studio, saved learning, and resume progress.

Phase 1 creates shared typed boundaries only. It does not implement P0 feature behaviour.

## User-group-to-feature mapping

| User group | Intended feature support | Boundary |
|---|---|---|
| Hearing-impaired learners | Transcript-first access and glossary recovery | These features do not claim to meet every access need. |
| Learners selecting cognitive-learning support | Focus Journey and Explain Differently | The learner selects needs; the system does not diagnose or infer disability. |
| Learners who want auditory reinforcement | Optional Read Along | It is not described as hearing support. |
| Both groups | Visual Story, trust controls, learning preferences | All controls remain learner-controlled. |

## Why Shravya is not a generic chatbot

Shravya does not expose open-ended chat or open-web retrieval. Future generated assets must be grounded only in verified transcripts, approved curriculum context, approved glossary terms, learning objectives, and approved teacher material. Every artifact will carry source, review, uncertainty, and stale status.

## Priorities

- **P0:** curriculum context through learning preferences, as listed in the approved plan.
- **P1:** Read Along, teacher review UI, Practice Studio, manual transcript editor, deletion.
- **P2:** Concept Map, broad question import, production privacy workflows, and multiple live providers.

The 90-second finale is built around the approved Class 7 Photosynthesis lesson.
