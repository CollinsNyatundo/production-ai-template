"""PM Toolkit & AI Shipping skills registry (6 skills)."""

TOOLKIT_AI_SHIP_SKILLS = {
    "draft-nda": {
        "name": "draft-nda",
        "title": "Non-Disclosure Agreement (NDA)",
        "icon": "🔐",
        "category": "Toolkit & AI Ship",
        "description": "Drafts detailed confidentiality agreement clauses for partnerships.",
        "prompt": (
            "Draft a Non-Disclosure Agreement (NDA): define confidential information types, exclusions, term duration,"
            " and jurisdiction clauses."
        ),
    },
    "privacy-policy": {
        "name": "privacy-policy",
        "title": "Privacy Policy Drafter",
        "icon": "📜",
        "category": "Toolkit & AI Ship",
        "description": "Drafts GDPR & CCPA compliant privacy policy clauses.",
        "prompt": (
            "Draft a privacy policy: cover data collection types, usage purpose, third-party sharing, GDPR/CCPA user"
            " rights, and contact info."
        ),
    },
    "grammar-check": {
        "name": "grammar-check",
        "title": "Grammar & Flow Proofreader",
        "icon": "✏️",
        "category": "Toolkit & AI Ship",
        "description": "Identifies grammar, logical, and tone errors without rewriting entire prose.",
        "prompt": (
            "Proofread text: suggest targeted grammar, tone, and logical clarity improvements without altering core"
            " author voice."
        ),
    },
    "review-resume": {
        "name": "review-resume",
        "title": "PM Resume Reviewer",
        "icon": "📄",
        "category": "Toolkit & AI Ship",
        "description": "Reviews PM resumes against XYZ+S impact formulas and keyword optimization.",
        "prompt": (
            "Review PM resume: apply Google's XYZ formula (Accomplished [X], as measured by [Y], by doing [Z]),"
            " optimize keywords, and improve structure."
        ),
    },
    "intended-vs-implemented": {
        "name": "intended-vs-implemented",
        "title": "Intended vs Implemented Audit",
        "icon": "🔬",
        "category": "Toolkit & AI Ship",
        "description": "Audits the gap between documented product intent and actual implementation code.",
        "prompt": (
            "Audit codebase against PRD specs: compare documented user/permission intent with source code logic to"
            " identify missing checks or scope drift."
        ),
    },
    "shipping-artifacts": {
        "name": "shipping-artifacts",
        "title": "Shipping Artifacts Packet",
        "icon": "📦",
        "category": "Toolkit & AI Ship",
        "description": "Generates durable documentation packet required for shipping AI-built software.",
        "prompt": (
            "Compile a durable AI shipping documentation packet: Architecture map, trust boundary security map,"
            " permission flows, env vars, and test coverage matrix."
        ),
    },
}
