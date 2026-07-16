# Phase 1 decisions

1. The application is structured as separate React/Vite frontend and FastAPI backend workspaces.
2. The prototype uses SQLite and UUID string primary keys; production storage is intentionally undecided.
3. The only development fixture is the approved Class 7 Science lesson, **Photosynthesis in Plants**. Its status is Demo, never Live.
4. The local role switch is a UI boundary, not authentication or tenancy.
5. User-facing strings are centralised and support English, Malayalam, and Malayalam-first bilingual rendering.
6. `GenerationPolicyService` and `ProvenanceService` are abstract service boundaries. Their future logic must be central rather than copied into routes.
7. Generated-artifact source concepts and references use association tables to support reliable stale-state handling.
8. No P0 feature behaviour is implemented in Phase 1. Screens are deliberately shell placeholders.
