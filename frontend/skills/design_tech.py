"""Design & Tech skills registry (10 skills)."""

DESIGN_TECH_SKILLS = {
    "frontend-design": {
        "name": "frontend-design",
        "title": "Frontend & UI Design",
        "icon": "🎨",
        "category": "Design & Tech",
        "description": "Guidance for distinctive visual design, typography, dark themes, and cardless layouts.",
        "prompt": (
            "Apply distinctive frontend design principles: use dark slate color themes, modern typography hierarchy,"
            " avoid AI slop, use intentional whitespace and smooth micro-interactions."
        ),
    },
    "doc-coauthoring": {
        "name": "doc-coauthoring",
        "title": "Doc Co-Authoring",
        "icon": "📝",
        "category": "Design & Tech",
        "description": "Guided workflow for co-authoring tech specs, proposals, and architecture decision records.",
        "prompt": (
            "Guide documentation creation through structured sections, explicit trade-offs, and clear acceptance"
            " criteria."
        ),
    },
    "web-artifacts-builder": {
        "name": "web-artifacts-builder",
        "title": "Web Artifacts Builder",
        "icon": "💻",
        "category": "Design & Tech",
        "description": "Builds multi-component interactive HTML/React/Tailwind artifacts.",
        "prompt": ("Format code as complete, self-contained interactive web artifacts with modern state management."),
    },
    "mcp-builder": {
        "name": "mcp-builder",
        "title": "MCP Server Builder",
        "icon": "🔌",
        "category": "Design & Tech",
        "description": "Architecture reference for creating Model Context Protocol servers in Python & TypeScript.",
        "prompt": (
            "Design high-quality MCP servers following official protocol specs, tool schemas, and typed context"
            " handlers."
        ),
    },
    "docx": {
        "name": "docx",
        "title": "Word (.docx) Handler",
        "icon": "📄",
        "category": "Design & Tech",
        "description": "Creates, parses, formats, and edits structured Word (.docx) documents.",
        "prompt": (
            "Structure text for Word document generation with formal heading hierarchies, tables, and callouts."
        ),
    },
    "pptx": {
        "name": "pptx",
        "title": "Slide Deck (.pptx)",
        "icon": "📊",
        "category": "Design & Tech",
        "description": "Generates slide deck layouts, pitch presentations, and visual cards.",
        "prompt": (
            "Design presentation slides with concise headlines, strong visual hierarchy, and 3-bullet limits per slide."
        ),
    },
    "xlsx": {
        "name": "xlsx",
        "title": "Spreadsheet (.xlsx)",
        "icon": "📈",
        "category": "Design & Tech",
        "description": "Analyzes, cleans, structures, and computes formulas for spreadsheets.",
        "prompt": "Format tabular data cleanly, generate robust spreadsheet formulas, and validate data types.",
    },
    "pdf": {
        "name": "pdf",
        "title": "PDF Processor",
        "icon": "📑",
        "category": "Design & Tech",
        "description": "Extracts, merges, splits, and formats structured PDF content.",
        "prompt": "Parse and format document text with clean markdown tables and extracted section references.",
    },
    "systematic-debugging": {
        "name": "systematic-debugging",
        "title": "Systematic Debugging",
        "icon": "🐞",
        "category": "Design & Tech",
        "description": "Empirical root-cause analysis, stack trace inspection, and evidence-first debugging.",
        "prompt": (
            "Follow systematic debugging: inspect full un-truncated logs, form empirical hypotheses, and verify fixes"
            " before declaring success."
        ),
    },
    "security-auditor": {
        "name": "security-auditor",
        "title": "Security Auditor",
        "icon": "🛡️",
        "category": "Design & Tech",
        "description": "Audits OWASP Top 10, prompt injection, authorization boundaries, and secret leakage.",
        "prompt": (
            "Audit code for security: check input sanitization, multi-tenant session isolation, and secret redaction."
        ),
    },
}
