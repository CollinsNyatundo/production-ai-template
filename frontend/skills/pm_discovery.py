"""PM Product Discovery skills registry (13 skills)."""

PM_DISCOVERY_SKILLS = {
    "opportunity-solution-tree": {
        "name": "opportunity-solution-tree",
        "title": "Opportunity Solution Tree",
        "icon": "🌲",
        "category": "PM Discovery",
        "description": "Teresa Torres OST mapping outcomes to customer opportunities, solutions, and experiments.",
        "prompt": (
            "Structure continuous product discovery using Teresa Torres' Opportunity Solution Tree: anchor to one"
            " desired outcome, map sub-opportunities, solutions, and assumption tests."
        ),
    },
    "brainstorm-ideas-new": {
        "name": "brainstorm-ideas-new",
        "title": "Product Trio Ideation (New)",
        "icon": "💡",
        "category": "PM Discovery",
        "description": "Ideation combining PM, Product Designer, and Engineer viewpoints for new products.",
        "prompt": (
            "Brainstorm feature solutions for new products using Product Trio perspectives (PM value, Designer UX,"
            " Engineer technical leverage)."
        ),
    },
    "brainstorm-ideas-existing": {
        "name": "brainstorm-ideas-existing",
        "title": "Product Trio Ideation (Existing)",
        "icon": "⚡",
        "category": "PM Discovery",
        "description": "Ideation combining PM, Designer, and Engineer perspectives for existing products.",
        "prompt": (
            "Brainstorm solution improvements for an existing product using PM, Design, and Engineering angles."
        ),
    },
    "brainstorm-experiments-new": {
        "name": "brainstorm-experiments-new",
        "title": "Pretotype Experiments (New)",
        "icon": "🧪",
        "category": "PM Discovery",
        "description": "Lean startup pretotypes (XYZ hypotheses) for validating new product ideas cheaply.",
        "prompt": (
            "Design pretotype validation experiments: write XYZ hypotheses (At least X% of Y will Z) with landing"
            " page/fake door tests."
        ),
    },
    "brainstorm-experiments-existing": {
        "name": "brainstorm-experiments-existing",
        "title": "Feature Experiments (Existing)",
        "icon": "🔬",
        "category": "PM Discovery",
        "description": "Low-effort validation experiments for feature ideas in existing products.",
        "prompt": "Design low-effort feature experiments: prototypes, concierge tests, and A/B spikes.",
    },
    "identify-assumptions-new": {
        "name": "identify-assumptions-new",
        "title": "Assumption Mapping (New)",
        "icon": "🔍",
        "category": "PM Discovery",
        "description": "Surfaces risky hidden assumptions across 8 startup risk categories.",
        "prompt": (
            "Identify risky assumptions across 8 startup categories: Value, Usability, Feasibility, Viability, GTM,"
            " Strategy, Financial, Team."
        ),
    },
    "identify-assumptions-existing": {
        "name": "identify-assumptions-existing",
        "title": "Assumption Mapping (Existing)",
        "icon": "🧐",
        "category": "PM Discovery",
        "description": "Devil's advocate assumption mapping for feature ideas in existing products.",
        "prompt": (
            "Stress-test feature ideas using devil's advocate thinking to surface hidden Value, Usability, Feasibility,"
            " and Viability assumptions."
        ),
    },
    "prioritize-assumptions": {
        "name": "prioritize-assumptions",
        "title": "Prioritize Assumptions",
        "icon": "⚖️",
        "category": "PM Discovery",
        "description": "Ranks assumptions on Impact × Risk matrix to select the cheapest validation experiments.",
        "prompt": (
            "Map assumptions on an Impact × Risk 2x2 matrix to isolate top leap-of-faith assumptions for low-effort"
            " pretotype testing."
        ),
    },
    "interview-script": {
        "name": "interview-script",
        "title": "Mom Test Interview Script",
        "icon": "🎙️",
        "category": "PM Discovery",
        "description": "Mom Test compliant interview scripts focusing on past user behavior instead of pitches.",
        "prompt": (
            "Draft customer interview scripts using Rob Fitzpatrick's The Mom Test: no leading questions, no pitches,"
            " probe past behavior and actual workarounds."
        ),
    },
    "summarize-interview": {
        "name": "summarize-interview",
        "title": "Interview Synthesizer",
        "icon": "📋",
        "category": "PM Discovery",
        "description": "Synthesizes customer transcripts into Jobs-to-be-Done (JTBD), pains, gains, and action items.",
        "prompt": (
            "Extract structured customer insights from transcripts: core JTBD, emotional pain triggers, existing"
            " workarounds, and non-obvious quotes."
        ),
    },
    "prioritize-features": {
        "name": "prioritize-features",
        "title": "Feature Backlog Prioritization",
        "icon": "📊",
        "category": "PM Discovery",
        "description": "Ranks backlog features using RICE, ICE, Kano, or Opportunity Scoring models.",
        "prompt": (
            "Prioritize feature backlog items using quantitative scoring (RICE: Reach × Impact × Confidence / Effort or"
            " Kano categorization)."
        ),
    },
    "analyze-feature-requests": {
        "name": "analyze-feature-requests",
        "title": "Feature Request Triager",
        "icon": "📥",
        "category": "PM Discovery",
        "description": "Analyzes customer feature requests by theme, strategic alignment, impact, and effort.",
        "prompt": (
            "Triage customer feature requests: group by core theme, assess strategic fit, rank by impact vs effort, and"
            " flag high-risk requests."
        ),
    },
    "metrics-dashboard": {
        "name": "metrics-dashboard",
        "title": "Metrics Dashboard Design",
        "icon": "📈",
        "category": "PM Discovery",
        "description": "Defines product metrics dashboard with KPIs, telemetry sources, and alert thresholds.",
        "prompt": (
            "Design a product metrics dashboard: define core KPIs, data pipeline sources, visualization charts, and"
            " alert thresholds."
        ),
    },
}
