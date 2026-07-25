"""PM Research & Data Analytics skills registry (10 skills)."""

RESEARCH_DATA_SKILLS = {
    "market-sizing": {
        "name": "market-sizing",
        "title": "TAM / SAM / SOM Market Sizing",
        "icon": "📏",
        "category": "Research & Data",
        "description": "Calculates Total Addressable Market using top-down and bottom-up models.",
        "prompt": (
            "Calculate market size estimates using both Top-Down industry reports and Bottom-Up (Price × Target"
            " Customers) methods for TAM, SAM, and SOM."
        ),
    },
    "competitor-analysis": {
        "name": "competitor-analysis",
        "title": "Competitor Landscape",
        "icon": "🕵️",
        "category": "Research & Data",
        "description": "Maps direct/indirect competitors, feature gaps, and differentiation opportunities.",
        "prompt": (
            "Perform competitive audit: map direct vs indirect competitors, compare pricing/features, and highlight"
            " sustainable differentiation vectors."
        ),
    },
    "customer-journey-map": {
        "name": "customer-journey-map",
        "title": "Customer Journey Map",
        "icon": "🎢",
        "category": "Research & Data",
        "description": "Maps user touchpoints, emotional highs/lows, friction points, and opportunities.",
        "prompt": (
            "Map the end-to-end customer journey: stages (Awareness, Onboarding, Use, Retention), touchpoints, emotional"
            " curve, and friction pain points."
        ),
    },
    "user-personas": {
        "name": "user-personas",
        "title": "User Personas Generator",
        "icon": "👤",
        "category": "Research & Data",
        "description": "Creates 3 research-grounded personas with JTBD, pain points, and gains.",
        "prompt": (
            "Develop 3 realistic user personas grounded in research data, detailing demographics, core JTBD, main"
            " friction points, and key buying triggers."
        ),
    },
    "market-segments": {
        "name": "market-segments",
        "title": "Market Segmentation",
        "icon": "🧩",
        "category": "Research & Data",
        "description": "Identifies 3-5 potential customer segments with demographics and product fit.",
        "prompt": (
            "Identify 3-5 distinct market segments: evaluate segment size, pain intensity, willingness-to-pay, and"
            " product-market fit."
        ),
    },
    "user-segmentation": {
        "name": "user-segmentation",
        "title": "User Behavioral Segmentation",
        "icon": "📊",
        "category": "Research & Data",
        "description": "Segments existing user base by usage patterns, JTBD, and satisfaction.",
        "prompt": (
            "Segment user feedback data into distinct behavioral cohorts based on usage frequency, feature reliance,"
            " and JTBD motivations."
        ),
    },
    "sentiment-analysis": {
        "name": "sentiment-analysis",
        "title": "Customer Feedback Sentiment",
        "icon": "💬",
        "category": "Research & Data",
        "description": "Analyzes large-scale user feedback for sentiment scores, JTBD, and NPS themes.",
        "prompt": (
            "Analyze customer feedback and reviews: categorize sentiment scores, extract top positive/negative themes,"
            " and map to JTBD needs."
        ),
    },
    "ab-test-analysis": {
        "name": "ab-test-analysis",
        "title": "A/B Test Evaluator",
        "icon": "🧪",
        "category": "Research & Data",
        "description": "Calculates statistical significance, confidence intervals, and Ship/Stop advice.",
        "prompt": (
            "Analyze split test results: calculate statistical significance (p-value, 95% CI), sample size validity,"
            " and recommend Ship, Extend, or Stop decisions."
        ),
    },
    "cohort-analysis": {
        "name": "cohort-analysis",
        "title": "Cohort Retention Analysis",
        "icon": "📊",
        "category": "Research & Data",
        "description": "Analyzes user retention curves, feature adoption, and churn patterns over time.",
        "prompt": (
            "Perform cohort analysis: analyze N-day retention curves, identify retention flatten points, and isolate"
            " feature usage correlations with long-term retention."
        ),
    },
    "sql-queries": {
        "name": "sql-queries",
        "title": "SQL Query Generator",
        "icon": "💾",
        "category": "Research & Data",
        "description": "Generates optimized SQL queries for BigQuery, PostgreSQL, MySQL, and Snowflake.",
        "prompt": (
            "Generate optimized SQL queries for data analytics: write clean SELECTs with appropriate JOINs, window"
            " functions, and CTEs."
        ),
    },
}
