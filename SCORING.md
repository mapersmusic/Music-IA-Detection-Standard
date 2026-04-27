# 📊 Scoring System — Music AI Detection Standard
*v0.1 — April 2026*

This document defines how to calculate a suspicion score from the criteria listed in `CRITERIA.md` and how to reach a final verdict.

---

## 1. Score Calculation

Each triggered criterion adds points to the total score. Protective factors subtract points.

### Primary Indicators (High Weight) — +3 pts each

| Criterion | Triggered? | Points |
| :--- | :---: | :---: |
| Release Velocity Burst (sudden spike after 2022) | ☐ | +3 |
| Raw Velocity Threshold (> 30 tracks/year) | ☐ | +3 |
| Missing Songwriter Credits on vocal tracks | ☐ | +3 |
| Lack of Real-World Presence (no concerts, no interviews) | ☐ | +3 |
| Copied Metadata (identical credits across 100+ tracks) | ☐ | +3 |

### Secondary Indicators (Medium Weight) — +1 pt each

| Criterion | Triggered? | Points |
| :--- | :---: | :---: |
| AI-Generated Artwork (artifacts confirmed by tool or moderator) | ☐ | +1 |
| Loudness Anomalies (abnormally low levels on YouTube Music) | ☐ | +1 |
| Distribution Patterns (linked to known mass-upload operators) | ☐ | +1 |
| Database Absence (> 20 tracks, zero MusicBrainz entries) | ☐ | +1 |
| Solo Credits on Mass Catalog (all roles: writing, mixing, producing) | ☐ | +1 |

### Protective Factors (Green Flags) — −3 pts each

| Factor | Present? | Points |
| :--- | :---: | :---: |
| Pre-2020 Release History (verifiable on Discogs, MusicBrainz, etc.) | ☐ | −3 |
| Verified Live Footprint (documented concerts, tours, or physical media) | ☐ | −3 |

---

## 2. Velocity Threshold Detail

The Raw Velocity criterion uses the following graduated scale:

| Tracks / Year | Status | Points Applied |
| :--- | :--- | :---: |
| < 15 | 🟢 Normal — no investigation needed | 0 |
| 15 – 30 | 🟡 Suspicious — check secondary criteria | +1 (secondary weight) |
| > 30 | 🔴 High Alert — apply primary weight | +3 (primary weight) |
| Sudden Spike post-2022 | 🔴 Critical — immediate priority review | +3 (primary weight, stacks) |

> ⚠️ A sudden spike and a high raw velocity can both be triggered simultaneously, for a combined +6.

---

## 3. Verdict Table

| Total Score | Verdict | Badge |
| :---: | :--- | :---: |
| ≤ 2 | **Human Artist** — no suspicious signal detected | 🟢 |
| 3 – 6 | **Unverified** — ambiguous signals, review in progress | 🟡 |
| ≥ 7 | **AI Probable** — high suspicion, validated by manual review | 🔴 |

> A verdict of **AI Probable** is never automatic. A score ≥ 7 triggers a mandatory human moderation review before any public label is applied.

---

## 4. Worked Example

**Fictional artist: "Ambient Skies"**

| Criterion | Triggered | Points |
| :--- | :---: | :---: |
| Raw Velocity Burst: 0 → 340 tracks in 14 months | ✅ | +3 |
| Raw Velocity Threshold: ~290 tracks/year | ✅ | +3 |
| Missing Songwriter Credits on all vocal tracks | ✅ | +3 |
| No live performances, no interviews found | ✅ | +3 |
| AI-generated artwork confirmed | ✅ | +1 |
| Zero MusicBrainz entries (380 tracks total) | ✅ | +1 |
| Pre-2020 history | ❌ | 0 |
| Verified live footprint | ❌ | 0 |
| **Total** | | **+14** |

**Verdict: 🔴 AI Probable** — forwarded to human moderation.

---

## 5. False Positive Protection

Before applying a 🔴 verdict, the moderator must verify:

- The artist has been given the opportunity to provide evidence of human identity (see `CONTRIBUTING.md` — *Reporting Edge Cases*).
- No single criterion alone is sufficient for a 🔴 verdict, regardless of its weight.
- New artists with no pre-2020 history are not penalized for their emergence date. The absence of a pre-2020 history is a **neutral** signal, not a negative one — only its confirmed absence alongside multiple other red flags contributes to the score.

---

## 6. Versioning

| Version | Date | Changes |
| :--- | :--- | :--- |
| v0.1 | April 2026 | Initial scoring framework |

*Thresholds and weights are subject to revision as new data and edge cases are reported by the community.*
