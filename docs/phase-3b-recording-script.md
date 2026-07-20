# Phase 3B recording script specification

The approved bundled WAV is a team-recorded Malayalam/code-mixed classroom demonstration. Its deterministic transcript is deliberately mapped offline; it is not live STT.

## Spoken script and timing

| Segment | Target time | Exact spoken text |
| --- | --- | --- |
| 1 | 0–7654 ms | `സസ്യങ്ങൾക്ക് ജലം, carbon dioxide, sunlight എന്നിവ ആവശ്യമാണ്.` |
| 2 | 7654–12988 ms | `ഇലയിലെ chlorophyll സൂര്യപ്രകാശം പിടിച്ചെടുക്കുന്നു.` |
| 3 | 12988–19400 ms | `Plants glucose നിർമ്മിക്കുകയും oxygen പുറത്തുവിടുകയും ചെയ്യുന്നു.` |

The speaker must pronounce **`chlorophyll`** correctly in segment 2. The bundled deterministic raw transcript intentionally renders that same spoken word as **`chlorophil`** to demonstrate a transcript misrecognition. Teacher review corrects it to **`Chlorophyll / ക്ലോറോഫിൽ`**. This is transcript error handling, never a direction for the speaker to make an error.

The prepared WAV duration is exactly 19400 ms. Do not insert music, tones, or silence that changes the stated timestamps.

## Recording guidance

One clear adult speaker recorded this small, deterministic classroom fixture. Use Malayalam-first pronunciation, with the English scientific terms spoken clearly and at a calm classroom pace.

The recording must contain no learner names, student voices, personal information, classroom identifiers, or other sensitive material. Obtain recorded-speaker consent where applicable and retain licence/consent evidence outside the application repository.

## Replacement manifest

The committed `photosynthesis-demo.wav.json` records the exact filename, SHA-256, parsed WAV properties, deterministic transcript mapping, and transparent offline provenance. Do not claim live STT accuracy or confidence.

## Human acceptance checklist

- Audible speech is present; the file is not tone-only content.
- Each segment’s words match the script and timing in the manifest.
- `chlorophyll` is clearly audible and correctly pronounced in segment 2.
- The raw deterministic fixture transcript still contains `chlorophil`.
- The demonstration represents transcript misrecognition, not speaker error.
- Playback is clean, at a suitable volume, with no clipping or distracting noise.
- The parsed total duration is exactly 19400 ms.
- No personal, learner, or student information is present.
- Consent and licence conditions permit the intended offline demo distribution.
