from app.services.deep_research.adversarial.synthesis_referee import SynthesisReferee
from app.services.deep_research.global_context import GlobalResearchContext
from app.services.llm_client import llm_client


class OneShotReportSynthesizer:
    """One-Shot Cohesive Report Generator with Synthesis Referee integration."""

    def __init__(self) -> None:
        self.referee = SynthesisReferee()

    async def generate_report(self, grc: GlobalResearchContext) -> str:
        """Synthesizes the mature GlobalResearchContext into a PhD-level research report."""
        core_facts, risk_facts = self.referee.arbitrate_and_structure(grc)
        risk_matrix = self.referee.generate_risk_matrix_markdown(risk_facts)

        context_prompt = grc.get_summary_text()

        prompt = (
            f"You are an Elite Academic & Executive Research Writer.\n"
            f"Generate a comprehensive, PhD-level research report based on this mature Global Research Context:\n\n"
            f"{context_prompt}\n\n"
            f"REQUIRED REPORT STRUCTURE:\n"
            f"# Executive Deep Research Report: {grc.original_query}\n\n"
            f"## 1. Executive Summary & Strategic Overview\n"
            f"## 2. Core Technical Architecture & Mechanics\n"
            f"## 3. Empirical Performance & Comparative Analysis\n"
            f"## 4. Evidence & Citation Appendix\n\n"
            f"Synthesize clearly, factually, and thoroughly."
        )

        try:
            resp = await llm_client.chat(
                messages=[
                    {"role": "system", "content": "You synthesize PhD-level academic research reports."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            report_body = (
                resp.choices[0].message.content or f"# Research Report: {grc.original_query}\n\nNo content generated."
            )
        except Exception as err:
            report_body = (
                f"# Executive Deep Research Report: {grc.original_query}\n\n"
                f"## 1. Executive Summary\n"
                f"Automated synthesis fallback for research topic: **{grc.original_query}**.\n\n"
                f"## 2. Key Verified Findings\n"
                f"{context_prompt}\n\n"
                f"*Synthesis engine exception details: {err}*"
            )

        # Append the adversarial Risk & Counter-Evidence Matrix
        return f"{report_body}\n\n{risk_matrix}"
