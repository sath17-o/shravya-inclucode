# Reading and comfort settings

## Scope and persistence

Reading preferences are browser-level student presentation choices. They are
stored separately from the context-scoped Focus Journey v5 record at
`shravya:student:reading-preferences` with `schemaVersion: 1`. This means a
lesson approval, context-version change, support-mode change, recovery state,
or Focus Journey restart can invalidate or reset learning progress without
changing the student's reading choices. `Reset reading settings` only restores
the preferences in this key; it does not touch the Focus Journey storage key.

The student boundary is provided by `StudentReadingPreferencesProvider` around
`/student` and `/student/focus` only. Teacher routes are deliberately outside
that boundary. The same reusable `ReadingSettingsPanel` appears in the normal
lesson's quiet “Help me focus” area and in Focus Journey's `More` utility
drawer. The reading reset is visually separated from `Restart journey` and its
helper text explicitly says that lesson progress is preserved.

The stored object is normalized to the semantic, bounded values below. Missing,
old partial, malformed, or unknown values deterministically produce the safe
v1 defaults. Normalization is idempotent. The preference record never embeds
course, context, answer, support-mode, recovery, or teacher data.

```ts
{
  schemaVersion: 1,
  font: "default" | "hyperlegible",
  textSize: "small" | "default" | "large" | "extra-large",
  spacing: "compact" | "default" | "wide",
  contrast: "default" | "high" | "dark",
  reduceMotion: boolean,
}
```

## Local fonts and provenance

No runtime font request or CDN is used. The assets below are bundled in the
frontend and use `font-display: swap`. “Upstream snapshot” is intentional: the
source filenames do not embed a release version, so the retained checksum
identifies the exact reviewed asset.

| Family | Asset | Source and original filename | License | SHA-256 |
| --- | --- | --- | --- | --- |
| Atkinson Hyperlegible (upstream snapshot) | `frontend/src/assets/fonts/AtkinsonHyperlegible-Regular.ttf` | [Braille Institute / Google Fonts source](https://github.com/googlefonts/atkinson-hyperlegible), `AtkinsonHyperlegible-Regular.ttf` | SIL OFL-1.1; retained at `frontend/src/assets/fonts/Atkinson-Hyperlegible-OFL.txt` | `7fb917c89019896d0b52ee84b7cbb3304c18cb90b19a62f5e32712bd23e97669` |
| Noto Sans Malayalam (upstream variable-font snapshot) | `frontend/src/assets/fonts/NotoSansMalayalam-wdth-wght.ttf` | [Google Fonts source](https://github.com/google/fonts/tree/main/ofl/notosansmalayalam), `NotoSansMalayalam[wdth,wght].ttf` | SIL OFL-1.1; retained at `frontend/src/assets/fonts/Noto-Sans-Malayalam-OFL.txt` | `312e0e7c3cc15fa09eb42a8f749eeb246b593ed420e3c81aafe8d910c3a6fb56` |

In easier-to-distinguish mode the stack puts Atkinson Hyperlegible before Noto
Sans Malayalam. Latin glyphs therefore resolve through Atkinson when present,
while Malayalam falls through to Noto Sans Malayalam. Existing reliable
Malayalam boundaries retain `lang="ml"`; bilingual components also retain a
separate `lang="en"` boundary for English. Wide spacing changes Latin letter
spacing only. Malayalam keeps normal letter spacing while inheriting the
larger line height and block spacing.

## Student design tokens and contrast evidence

The student-only boundary controls font family, font scale, Latin letter
spacing, line height, block spacing, background, surface, foreground, muted
foreground, border, and focus colours. Text sizes are bounded presets; wide
spacing increases vertical rhythm rather than Malayalam letter spacing.

Calculated WCAG contrast ratios for the controlled token pairs are:

| Mode | Foreground / background | Ratio |
| --- | --- | ---: |
| Default body | `#17332d` / `#f5f5ef` | 12.40:1 |
| Default muted copy | `#42665c` / `#f5f5ef` | 5.84:1 |
| High contrast body | `#000000` / `#ffffff` | 21.00:1 |
| High contrast muted copy | `#222222` / `#ffffff` | 15.91:1 |
| High contrast focus | `#003cff` / `#ffffff` | 6.80:1 |
| Dark body | `#f9fffa` / `#17352c` | 13.09:1 |
| Dark muted copy | `#c8ded4` / `#17352c` | 9.39:1 |
| Dark focus / primary action | `#10251f` / `#ffd166` | 11.15:1 |
| Dark border | `#98b8a8` / `#17352c` | 6.17:1 |

Selected controls retain the native checked state and a thicker, high-contrast
border; focus remains an outline rather than a colour-only distinction. The
student setting disables animations, transitions, and smooth scrolling when
enabled. The existing operating-system `prefers-reduced-motion` media rule
continues to apply independently.

## Automated coverage and required human review

Automated tests cover normalization/migration, isolated reset behaviour,
student-only boundary scope, semantic controls, persistence across reload, and
large/wide desktop layout without horizontal scrolling. They do not certify
human readability or Malayalam shaping.

Ticket A automated verification on 2026-07-23 completed with `npm.cmd
--prefix frontend run lint`, `npm.cmd --prefix frontend test -- --run` (80
tests), `npm.cmd --prefix frontend run build`, and `npm.cmd exec playwright
test -- --reporter=line` from `frontend` (8 browser tests), all with exit code
0. No backend or shared contract changed, so the backend suite was not run for
this presentation-only ticket.

The following remain **PENDING HUMAN CHECK**:

- lowercase `l`, uppercase `I`, and numeral `1` are visually distinguishable;
- Malayalam conjuncts, vowel signs, combining marks, and mixed-script
  baselines remain correct in default and wide spacing;
- largest text plus wide spacing is comfortable and unclipped on the target
  laptop;
- high-contrast and dark modes are visually acceptable;
- focus indicators remain plainly visible;
- reduced motion feels static;
- the quiet lesson placement is discoverable;
- reading reset is clearly distinct from progress restart; and
- teacher pages are visually unchanged.

Malayalam shaping validation owner: **Phase 4D Malayalam-reading specialist — PENDING**.

## Known MVP limitation

There is intentionally no new top-level reading-settings destination. In the
ordinary lesson the panel is a disclosure in the existing quiet “Help me
focus” area; in Focus Journey it is under `More`. Discoverability of that
placement requires the human review listed above.
