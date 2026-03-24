"""Briefing text formatting templates."""


def format_briefing_section(title: str, items: list[str]) -> str:
    """Format a briefing section with title and bullet points."""
    lines = [f"**{title}**"]
    for item in items:
        lines.append(f"  • {item}")
    return "\n".join(lines)


def format_morning_briefing(sections: dict[str, list[str]]) -> str:
    """Format a complete morning briefing."""
    parts = ["Good morning! Here's your briefing:\n"]
    for title, items in sections.items():
        parts.append(format_briefing_section(title, items))
        parts.append("")
    return "\n".join(parts)
