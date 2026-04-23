# 🛠 Detection Criteria & Scoring Grid

This document defines the formal criteria used to evaluate the probability of AI-generated content within music catalogs. These indicators are based on behavioral patterns and metadata auditing rather than audio signal analysis.

## 1. Primary Indicators (High Weight)

These signals provide the strongest evidence of synthetic or "content farm" activity.

* **Release Velocity Burst (🔴 Very High)**: A drastic change in output frequency after 2022. Example: An artist with 2 albums in 6 years suddenly releasing 300+ tracks in 18 months.
* **Raw Velocity Threshold (🔴 High)**: Publishing more than 50 tracks per year is a critical signal for investigation. 
* **Missing Songwriter Credits (🔴 High)**: Vocal tracks where the performer is absent from composition/songwriter credits in official metadata (e.g., MusicBrainz, Spotify API), as human artists typically claim these royalties.
* **Lack of Real-World Presence (🔴 High)**: Complete absence of live performance history, video interviews, or verifiable non-AI photography.
* **Copied Metadata (🔴 High)**: Identical blocks of credits copy-pasted across hundreds of disparate tracks.

## 2. Secondary Indicators (Medium Weight)

These factors are usually evaluated in correlation with others to build a case.

* **AI-Generated Artwork (🟡 Medium)**: Systematic use of cover art featuring visible AI artifacts or confirmed through image detection tools.
* **Loudness Anomalies (🟡 Medium)**: Specifically on YouTube Music, AI tracks often exhibit significantly lower loudness levels due to non-standard normalization during the training/generation process.
* **Distribution Patterns (🟡 Medium)**: Metadata patterns associated with known high-volume AI mass-uploaders.
* **Database Absence (🟡 Medium)**: Large catalogs (>20 tracks) that are completely unreferenced on community-driven databases like MusicBrainz.
* **Solo Credits on Mass Catalogs (🟡 Medium)**: A single individual credited for every role (writing, composing, producing, mixing) on a very large vocal catalog with no external collaborators.

## 3. Protective Factors (Green Flags)

These indicators serve to protect human artists and reduce false positives.

* **Pre-2020 History (🟢 Protective)**: A verifiable history of releases prior to 2020 is a strong signal of human creativity, as high-fidelity AI music generation was not publicly available.
* **Verified Live Footprint (🟢 Protective)**: Documented concerts, tours, or physical media releases.

---

## 📈 Velocity Thresholds Summary

| Tracks / Year | Status | Action Required |
| :--- | :--- | :--- |
| < 15 | 🟢 Normal | No investigation needed |
| 15 – 50 | 🟡 Suspicious | Secondary criteria check |
| > 50 | 🔴 High Alert | Full investigation |
| Sudden Spike | 🔴 Critical | Immediate priority review |
