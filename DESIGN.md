# DESIGN.md — Stickman Generator Design System

> **Design Read:** Creative production studio & storyboard workbench for digital content creators (Shorts, Reels, YouTube), with an analog-tactile editorial language, holding **Dial: ENERGY 2 / RHYTHM 2 / MOTION 1**.
> 
> *Direction Notice:* Direction drafted by AI based on the product's functional workflow (story drafting to automated frame generation). In accordance with `antislop` guidelines, review and calibrate these design choices to reflect your unique product taste.

---

## 1. Product Identity & Vibe

**Stickman Generator** is not a generic enterprise dashboard; it is a **creative director's workbench**. It translates narrative scripts into visual storyboard frames for video creators.

* **Personality:** Tactile, focused, cinematic, and utilitarian. It feels like an animator's cutting room or a director's drafting table.
* **Core Metaphor:** *The Storyboard Reel* — distinct sequence cards, timecode markers, prompt crafting notes, and frame-by-frame production status.
* **Anti-Default Stance:** 
  - No purple-to-blue AI gradients or blurred background ambient glows.
  - No uniform pill-shaped buttons and inputs.
  - No decorative background dot-grids or pseudo-tech filler textures.
  - No glassmorphism stacking where everything is frosted and nothing is grounded.

---

## 2. Core Dials (Strictly Enforced)

| Dial | Level | Implementation for Stickman Generator |
|---|:---:|---|
| **ENERGY** | **2 (Balanced)** | Grounded dark workbench with crisp typographical contrast and one warm amber accent for primary creation. Neither sterile black/white nor noisy neon. |
| **RHYTHM** | **2 (Balanced)** | Asymmetric functional split (e.g. Script Editor / Storyboard Reel / Inspector dock) with predictable internal rhythm inside scene cards. |
| **MOTION** | **1 (Calm)** | Functional micro-interactions only: snappy tab switches, smooth reorder transitions, clear progress indicators. Zero infinite floating loops or gratuitous bouncy physics. |

---

## 3. Color Palette & Surface Hierarchy

Adhering to `antislop` rules (R-29: 2–3 core colors + 1 single deliberate accent):

### Base & Surfaces
* **Canvas Ground (`bg-canvas`):** `#0e1015` — Deep carbon graphite with a subtle warm undertone. Not pure `#000000` (which causes harsh contrast fatigue) and not default `#18181b` zinc.
* **Surface Layer 1 (`surface-raised`):** `#161920` — Panel containers, card groups, header dock.
* **Surface Layer 2 (`surface-card`):** `#1e222b` — Individual scene cards, dialog panels, active drop zones.
* **Borders & Dividers (`border-subtle`):** `#292e3b` — Crisp 1px hairline dividers; high definition without muddy grey haze.
* **Border Highlight (`border-active`):** `#3d4455` — Hover states and elevated cards.

### The Deliberate Accent (Amber Studio Ink)
* **Primary Accent (`accent-amber`):** `#f59e0b` (Amber 500) / `#d97706` (Amber 600 hover).
  - *Usage restriction:* Reserved strictly for the primary creative trigger ("Generate Cerita", "Konfirmasi & Generate"), the active Worker state indicator, and current active scene badge. It is never used as background flood or decorative lines.
* **Accent Foreground:** `#0e1015` on amber buttons for guaranteed WCAG AAA contrast ratio (> 9:1).

### Typographic Contrast (WCAG 2.2 AA compliant)
* **High Contrast / Primary:** `#f8fafc` (Slate 50) — Story narration, scene headings, active inputs.
* **Medium Contrast / Secondary:** `#94a3b8` (Slate 400) — Metadata, field labels, timestamps, prompt previews.
* **Low Contrast / Muted:** `#64748b` (Slate 500) — Placeholders, shortcut hints, subtle borders.

---

## 4. Typography System

* **Primary Typeface:** Clean, modern geometric sans (`Plus Jakarta Sans` or modern system fallback `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
* **Monospace / Timecodes:** Tabular figures (`ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace`).
  - Used for: Scene counters (`SCENE 01 / 12`), duration (`60s`, `00:45`), format aspect ratios (`9:16`, `16:9`), and file names (`scene_001.png`).

### Type Hierarchy
* **Screen Title:** `text-xl font-bold tracking-tight text-slate-100`
* **Card Heading / Sub-title:** `text-sm font-semibold tracking-normal text-slate-200`
* **Field Labels:** `text-xs font-medium uppercase tracking-wider text-slate-400`
* **Body / Narration Input:** `text-sm leading-relaxed text-slate-100`
* **Metadata & Captions:** `text-xs font-mono text-slate-400`

---

## 5. Components & Spatial Structure

### 5.1 Radii System (R-11)
Avoid uniform pill radius across all items:
* **Inputs & Standard Buttons:** `rounded-lg` (8px).
* **Panels & Storyboard Cards:** `rounded-xl` (12px).
* **Modals & Dialog Sheets:** `rounded-2xl` (16px).
* **Status Badges & Pills:** `rounded-md` (6px) or `rounded-full` only for indicator dots.

### 5.2 Elevation & Shadows (R-12)
* Most panels sit flat with hairline borders (`border border-[#292e3b]`).
* Modals and flying tooltips utilize deliberate dark drop shadows (`shadow-2xl shadow-black/60`).

### 5.3 Storyboard Card Architecture (The Core Workhorse)
Each scene in `DraftEditor` is treated as a **storyboard frame**:
* **Top Ribbon:** Scene number badge (`SCENE 01`), estimated read duration, reorder controls (`Up` / `Down`), and action buttons (`Insert`, `Delete`).
* **Main Script Block:** Split into two clear vertical columns/zones:
  1. *Narration (Spoken Word)* — The script that the narrator speaks.
  2. *Visual Direction (Prompt to Google Flow)* — What Google Flow will draw, formatted with subtle visual framing.
  3. *On-screen Title* — Text overlay if needed.

---

## 6. Functional Interactions & States

* **Buttons & CTAs:**
  - `Primary Action`: High contrast Amber (`bg-amber-500 hover:bg-amber-400 text-slate-950 font-medium active:scale-[0.99]`).
  - `Secondary Action`: Outlined slate (`bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700`).
  - `Ghost / Destructive`: Matte dark red hover (`hover:bg-red-500/10 hover:text-red-400 text-slate-400`).
* **Focus States:** Every interactive element has an explicit, accessible outline: `focus-visible:ring-2 focus-visible:ring-amber-500/50 focus-visible:outline-none`.
* **Disabled States:** `disabled:opacity-40 disabled:cursor-not-allowed`.
* **Worker Telemetry Indicator:**
  - `Worker Active`: Animated amber pulse indicator with clear status text.
  - `Worker Idle / Off`: Calm slate status with clear switch affordance.

---

## 7. Anti-Slop Pre-Flight Verification Checklist

Before deploying any redesigned screen:
- [ ] No generic purple/cyan gradient used anywhere.
- [ ] No decorative unmotivated background grid or ambient orb.
- [ ] Active palette constrained to 3 neutrals + 1 amber accent.
- [ ] All interactive buttons have explicit states (`hover`, `active`, `focus-visible`, `disabled`).
- [ ] Form controls and labels have high contrast (tested >= 4.5:1 text, >= 3:1 controls).
- [ ] Storyboard cards reflect real scene hierarchy, not copy-pasted generic cards.
