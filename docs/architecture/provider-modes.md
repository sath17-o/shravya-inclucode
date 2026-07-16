# Provider modes and exact-lesson cache policy

Phase 1 defines provider configuration only. No provider implementation or paid API call exists.

| Mode | Meaning | Permitted use |
|---|---|---|
| `live` | A configured external provider | Later approved production/finale use only |
| `cached` | Output previously generated from the exact approved lesson/audio and matching context | Offline recovery |
| `demo` | Deterministic local fixture | Development and automated tests |

Student-facing content must identify its status as Live, Cached, or Demo. A demo fixture is never presented as newly generated live content. Cached fallback must work with no network connection and must only be used for the same approved Photosynthesis lesson source/context revision.
