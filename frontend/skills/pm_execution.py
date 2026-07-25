"""PM Execution skills registry (16 skills)."""

PM_EXECUTION_SKILLS = {
    "create-prd": {
        "name": "create-prd",
        "title": "Product Requirements (PRD)",
        "icon": "📝",
        "category": "PM Execution",
        "description": "Comprehensive 8-section PRD covering problem, goals, scope boundaries, and release criteria.",
        "prompt": (
            "Draft a lightweight 8-section PRD: Problem statement, success metrics, user segments, solution scope,"
            " explicit non-goals, and release milestones."
        ),
    },
    "brainstorm-okrs": {
        "name": "brainstorm-okrs",
        "title": "OKR Generator",
        "icon": "🎯",
        "category": "PM Execution",
        "description": "Drafts qualitative Objectives with measurable, outcome-based Key Results.",
        "prompt": (
            "Write team OKRs: craft qualitative, inspiring Objectives paired with 3-5 quantitative, outcome-based Key"
            " Results."
        ),
    },
    "outcome-roadmap": {
        "name": "outcome-roadmap",
        "title": "Outcome-Based Roadmap",
        "icon": "🗺️",
        "category": "PM Execution",
        "description": "Transforms feature output roadmaps into strategic Now/Next/Later outcome roadmaps.",
        "prompt": (
            "Transform output feature roadmaps into Now/Next/Later Outcome Roadmaps organized by user/business"
            " impact objectives."
        ),
    },
    "sprint-plan": {
        "name": "sprint-plan",
        "title": "Sprint Planning Assistant",
        "icon": "🏃",
        "category": "PM Execution",
        "description": "Estimates team velocity, story breakdown, dependency risks, and sprint goal commitment.",
        "prompt": (
            "Plan sprint commitments: map team velocity, identify cross-team dependencies, and establish a single"
            " unified Sprint Goal."
        ),
    },
    "pre-mortem": {
        "name": "pre-mortem",
        "title": "Pre-Mortem Risk Analysis",
        "icon": "🐯",
        "category": "PM Execution",
        "description": "Categorizes launch risks into Real Tigers, Paper Tigers, and Unspoken Elephants.",
        "prompt": (
            "Conduct a launch Pre-Mortem: assume the product failed catastrophically 6 months after launch, categorize"
            " failure causes into Real Tigers, Paper Tigers, and Elephants."
        ),
    },
    "user-stories": {
        "name": "user-stories",
        "title": "INVEST User Stories",
        "icon": "📌",
        "category": "PM Execution",
        "description": "Creates INVEST user stories following 3 Cs (Card, Conversation, Confirmation).",
        "prompt": (
            "Write INVEST-compliant user stories: 'As a [persona], I want [capability] so that [benefit]' with clear"
            " Given/When/Then acceptance criteria."
        ),
    },
    "job-stories": {
        "name": "job-stories",
        "title": "JTBD Job Stories",
        "icon": "🔄",
        "category": "PM Execution",
        "description": "Creates job stories in 'When [situation], I want to [motivation], so I can [outcome]' format.",
        "prompt": (
            "Format JTBD backlog items: 'When [situation], I want to [motivation], so I can [outcome]' with explicit"
            " context triggers."
        ),
    },
    "stakeholder-map": {
        "name": "stakeholder-map",
        "title": "Stakeholder Matrix",
        "icon": "👥",
        "category": "PM Execution",
        "description": "Maps stakeholder Power × Interest grid and builds communication alignment plans.",
        "prompt": (
            "Create a Stakeholder Power vs Interest grid, defining tailored communication rhythms for Manage Closely,"
            " Keep Satisfied, Keep Informed, and Monitor quadrants."
        ),
    },
    "strategy-red-team": {
        "name": "strategy-red-team",
        "title": "Strategy Red-Teaming",
        "icon": "🥊",
        "category": "PM Execution",
        "description": "Attacks load-bearing strategy assumptions and identifies cheap kill criteria tests.",
        "prompt": (
            "Red-team the product strategy: steelman claims, attack load-bearing assumptions, and propose the cheapest"
            " test and kill criteria for each."
        ),
    },
    "prioritization-frameworks": {
        "name": "prioritization-frameworks",
        "title": "Prioritization Frameworks",
        "icon": "🧮",
        "category": "PM Execution",
        "description": "Guide to 9 prioritization models: RICE, ICE, Kano, MoSCoW, Opportunity Score, etc.",
        "prompt": (
            "Select and apply prioritization formulas (RICE, ICE, Kano, MoSCoW, Opportunity Score) with explicit"
            " step-by-step scoring."
        ),
    },
    "release-notes": {
        "name": "release-notes",
        "title": "User-Facing Release Notes",
        "icon": "📢",
        "category": "PM Execution",
        "description": "Generates engaging, user-facing release notes from PRDs or changelogs.",
        "prompt": (
            "Write clear user release notes grouped by New Features, Improvements, and Fixes with user benefits"
            " highlighted."
        ),
    },
    "retro": {
        "name": "retro",
        "title": "Sprint Retrospective",
        "icon": "🔁",
        "category": "PM Execution",
        "description": "Facilitates retrospective: what went well, what didn't, and actionable owners.",
        "prompt": (
            "Facilitate a Sprint Retrospective: summarize What Went Well, What Didn't, and generate SMART action items"
            " with assigned owners."
        ),
    },
    "summarize-meeting": {
        "name": "summarize-meeting",
        "title": "Meeting Transcript Summarizer",
        "icon": "📝",
        "category": "PM Execution",
        "description": "Summarizes meeting recordings into decisions, key points, and action items.",
        "prompt": (
            "Summarize meeting transcripts into Date, Attendees, Key Decisions, Summary Points, and Action Items with"
            " deadlines."
        ),
    },
    "test-scenarios": {
        "name": "test-scenarios",
        "title": "QA Test Scenarios",
        "icon": "🧪",
        "category": "PM Execution",
        "description": "Generates comprehensive QA test scenarios with starting conditions and expected outcomes.",
        "prompt": (
            "Generate QA test scenarios from user stories: define preconditions, step-by-step actions, and expected"
            " outcomes."
        ),
    },
    "dummy-dataset": {
        "name": "dummy-dataset",
        "title": "Dummy Dataset Generator",
        "icon": "🗄️",
        "category": "PM Execution",
        "description": "Generates realistic dummy data in CSV, JSON, SQL, or Python script format.",
        "prompt": (
            "Generate realistic dummy datasets with custom schema columns, realistic edge cases, and CSV/JSON output."
        ),
    },
    "wwas": {
        "name": "wwas",
        "title": "Why-What-Acceptance (WWA)",
        "icon": "📄",
        "category": "PM Execution",
        "description": "Creates backlog items in strategic Why-What-Acceptance format.",
        "prompt": (
            "Format backlog items in Why-What-Acceptance (WWA) format: Strategic Why, Solution What, and Testable"
            " Acceptance criteria."
        ),
    },
}
