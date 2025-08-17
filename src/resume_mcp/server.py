import sys
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import logging

# --- logging (stderr only, never stdout) ---
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# --- state / storage ---
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

STATE = {"resume_latex": None, "job_description": None}

def _save_text(name: str, text: str) -> str:
    path = DATA_DIR / name
    path.write_text(text, encoding="utf-8")
    return str(path)

# --- MCP server ---
mcp = FastMCP("resume-mcp")

@mcp.tool()
def set_resume_latex(latex: str):
    """Store the base LaTeX resume text."""
    STATE["resume_latex"] = latex
    return {"ok": True, "saved_to": _save_text("resume_base.tex", latex)}

@mcp.tool()
def set_job_description(text: str):
    """Store the job description text."""
    STATE["job_description"] = text
    return {"ok": True, "saved_to": _save_text("job_description.txt", text)}

@mcp.tool()
def generate_tailored_resume():
    """Generate a tailored resume by injecting the job description into the LaTeX."""
    resume, jd = STATE["resume_latex"], STATE["job_description"]
    if not resume:
        return {"ok": False, "error": "No resume set"}
    if not jd:
        return {"ok": False, "error": "No job description set"}

    summary = (
        "% --- auto-generated block ---\n"
        "\\section*{Target Role Summary}\n"
        "\\begin{itemize}\n"
        "\\item This tailored version emphasizes alignment with the provided job description.\n"
        "\\end{itemize}\n"
        "\\subsection*{Job Description}\n"
        "\\begin{verbatim}\n"
        f"{jd}\n"
        "\\end{verbatim}\n"
        "% --- end block ---\n\n"
    )

    marker = "\\begin{document}"
    if marker in resume:
        parts = resume.split(marker, 1)
        tailored = parts[0] + marker + "\n\n" + summary + parts[1]
    else:
        tailored = summary + resume

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = _save_text(f"resume_tailored_{ts}.tex", tailored)
    return {"ok": True, "output_path": out_path, "latex": tailored}

@mcp.tool()
def debug_state():
    """Check what’s loaded in memory."""
    return {"has_resume": STATE["resume_latex"] is not None,
            "has_jd": STATE["job_description"] is not None,
            "data_dir": str(DATA_DIR)}

if __name__ == "__main__":
    mcp.run(transport="stdio")
