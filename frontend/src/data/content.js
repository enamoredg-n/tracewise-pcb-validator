export const navLinks = [
  { label: "Overview", href: "#overview" },
  { label: "Pipeline", href: "#pipeline" },
  { label: "Parser", href: "#parser" },
  { label: "Use Cases", href: "#use-cases" },
];

export const heroStats = [
  { label: "Input fidelity", value: "KiCad + DXF" },
  { label: "Decision layer", value: "Rules + Reference + AI" },
  { label: "Delivery style", value: "Presentation-first workflow" },
];

export const pipelineSteps = [
  {
    title: "React Frontend",
    short: "UI",
    copy: "A presentation-grade validation console for uploads, presets, metrics, issues, and report delivery.",
  },
  {
    title: "Validation Controller",
    short: "VC",
    copy: "Coordinates parsing, presets, summaries, reference selection, and validation runs.",
  },
  {
    title: "PCB Parser",
    short: "PP",
    copy: "Reads KiCad and DXF sources into structured geometry instead of visual guesses.",
  },
  {
    title: "Rule Engine",
    short: "RE",
    copy: "Applies deterministic checks for board dimensions, drills, traces, spacing, and routing.",
  },
  {
    title: "Reference Compare",
    short: "RC",
    copy: "Highlights drift against an approved board to surface changes with engineering context.",
  },
  {
    title: "AI Copilot",
    short: "AI",
    copy: "Explains exact failures in plain language and suggests what to fix first.",
  },
];

export const featureSections = [
  {
    id: "parser",
    kicker: "PCB Parser",
    title: "The parser is the engine block that teaches the platform what the board really is.",
    description:
      "TraceWise reads actual `.kicad_pcb` and DXF design files, extracts geometry, routing, and structural board facts, and turns them into a clean truth layer for validation.",
    bullets: [
      "Real KiCad and DXF ingestion",
      "Board dimensions, drills, pads, traces, and nets",
      "A shared data model for rules, comparison, and reports",
    ],
    layout: "cards",
    cards: [
      {
        badge: "KiCad",
        title: "Native design intake",
        text: "Pulls setup values, trace data, hole information, and routing facts directly from the board file.",
      },
      {
        badge: "DXF",
        title: "Mechanical fallback support",
        text: "Keeps the workflow useful when geometry review happens before full board metadata is available.",
      },
      {
        badge: "Data",
        title: "Structured truth layer",
        text: "Creates a normalized representation so every downstream system reads the same design reality.",
      },
    ],
  },
  {
    id: "rule-engine",
    kicker: "Rule Engine",
    title: "Exact checks replace vague anomaly spotting with measurable engineering review.",
    description:
      "The rule layer turns parser facts into decisions across board geometry, drills, traces, spacing, and electrical integrity so the product feels dependable instead of speculative.",
    bullets: [
      "Board width, height, edge, and manufacturing safety",
      "Drill count, position, and minimum hole diameter",
      "Trace width, spacing, and ERC-style routing health",
    ],
    layout: "timeline",
    cards: [
      {
        badge: "01",
        title: "Board checks",
        text: "Verifies board size, edge conditions, and fabrication-aware geometry limits.",
      },
      {
        badge: "02",
        title: "Drill checks",
        text: "Flags risky hole diameters, unexpected count changes, and position drift.",
      },
      {
        badge: "03",
        title: "Trace + ERC checks",
        text: "Surfaces thin tracks, unsafe spacing, unrouted nets, and electrical regressions.",
      },
    ],
  },
  {
    id: "reference",
    kicker: "Reference",
    title: "Reference comparison tells the team what changed, not just what failed.",
    description:
      "A trusted baseline board anchors the review process so every new revision can be measured against approved geometry, drills, and placement.",
    bullets: [
      "Approved reference board vs candidate board",
      "Drill, component, and board-dimension drift",
      "Practical revision control for PCB teams",
    ],
    layout: "split",
    cards: [
      {
        badge: "Base",
        title: "Reference board",
        text: "A known-good revision becomes the comparison anchor for all future validation runs.",
      },
      {
        badge: "Diff",
        title: "Candidate review",
        text: "Each new board can be measured for movement, shape drift, and change intent.",
      },
      {
        badge: "Why",
        title: "Decision clarity",
        text: "The story shifts from isolated failures to revision-aware engineering decisions.",
      },
    ],
  },
  {
    id: "scope",
    kicker: "Scope",
    title: "The current scope is focused, credible, and designed to scale cleanly.",
    description:
      "Instead of chasing everything at once, the platform centers on the validation layers that matter most in early-stage PCB review and fabrication readiness.",
    bullets: [
      "Mechanical validation",
      "Manufacturing readiness",
      "Electrical health plus AI interpretation",
    ],
    layout: "grid",
    cards: [
      {
        badge: "M",
        title: "Mechanical",
        text: "Hole size, drill spacing, board dimensions, and component movement checks.",
      },
      {
        badge: "F",
        title: "Manufacturing",
        text: "Trace width, clearance, edge safety, and fabricatability-focused signals.",
      },
      {
        badge: "E",
        title: "Electrical",
        text: "Routing continuity, missing copper, and connection-health regression checks.",
      },
      {
        badge: "AI",
        title: "Interpretation Layer",
        text: "Severity summaries, plain-English guidance, and fix-first recommendations.",
      },
    ],
  },
  {
    id: "use-cases",
    kicker: "Potential Use",
    title: "The product fits engineering review moments where speed and confidence both matter.",
    description:
      "TraceWise works best when a team needs early design feedback, drift awareness, and a polished way to explain technical findings to stakeholders.",
    bullets: [
      "Prototype review before fabrication",
      "Revision drift monitoring for active programs",
      "Presentation-ready reporting for mixed audiences",
    ],
    layout: "cards",
    cards: [
      {
        badge: "Gate",
        title: "Pre-fabrication review",
        text: "Catch board issues before fabrication review becomes a slower, more expensive checkpoint.",
      },
      {
        badge: "Flow",
        title: "Design-change control",
        text: "Keep moving revisions aligned with approved references instead of relying on memory.",
      },
      {
        badge: "Demo",
        title: "Stakeholder communication",
        text: "Turn exact failures into a story executives, leads, and reviewers can follow quickly.",
      },
    ],
  },
];

export const validationCards = [
  {
    step: "01",
    title: "Upload the board",
    text: "Bring in a candidate `.kicad_pcb` or `.dxf` file and establish a clean input baseline.",
  },
  {
    step: "02",
    title: "Run exact checks",
    text: "Apply board, drill, trace, spacing, and electrical rules with deterministic output.",
  },
  {
    step: "03",
    title: "Compare references",
    text: "Use an approved board to catch revision drift across dimensions, drills, and placement.",
  },
  {
    step: "04",
    title: "Explain priorities",
    text: "Layer in AI guidance after the rules speak, so the explanation stays grounded.",
  },
];
