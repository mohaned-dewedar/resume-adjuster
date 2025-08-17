"""
Improved Resume MCP Server using resources and structured output.
"""
import sys
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List
from pydantic import BaseModel, Field
import re
from mcp.server.fastmcp import FastMCP

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("resume-mcp")

# -----------------------------
# Storage
# -----------------------------
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = DATA_DIR / "prompts"
DATA_DIR.mkdir(exist_ok=True)
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

# State
STATE = {
    "resume_latex": None,
    "job_description": None,
    "company": None,
    "company_brief": None,
}

def _now_ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def _save_text(name: str, text: str) -> str:
    """Save text under data/ and return absolute path as string."""
    p = DATA_DIR / name
    p.write_text(text, encoding="utf-8")
    return str(p)

# -----------------------------
# Structured Output Models
# -----------------------------
class ResumeStatus(BaseModel):
    """Status of resume tailoring workflow."""
    has_resume: bool = Field(description="Whether base resume is loaded")
    has_job_description: bool = Field(description="Whether job description is loaded")
    company: Optional[str] = Field(description="Company name if set")
    has_company_brief: bool = Field(description="Whether company research is available")
    ready_for_generation: bool = Field(description="Whether ready to generate tailored resume")

class CompilationResult(BaseModel):
    """Result of PDF compilation."""
    success: bool = Field(description="Whether compilation succeeded")
    pdf_path: Optional[str] = Field(description="Path to generated PDF")
    tex_path: str = Field(description="Path to source TEX file")
    error_message: Optional[str] = Field(description="Error message if compilation failed")

# -----------------------------
# Prompt defaults
# -----------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are an expert resume tailor for Applicant Tracking Systems (ATS). "
    "Rewrite LaTeX resumes to align with a given job description and company context. "
    "Keep outputs ATS-friendly (minimal packages/macros), concise, factually accurate, and impact-focused. "
    "Bias for exactly one page whenever possible. When ready, return your final answer by calling the "
    "'submit_tailored_resume' tool with structured arguments."
)

DEFAULT_USER_TEMPLATE = """Task:
- Read the candidate's current LaTeX resume and the job description.
- Use the company brief (if present) for terminology and emphasis.
- Produce an updated ATS-friendly LaTeX resume tailored to the role.

Output rules:
- Do NOT print the LaTeX directly. When finished, call the tool 'submit_tailored_resume' with:
  - filename_stem: lower_snake_case like 'resume_<role>_<company>' (only [a-z0-9_], under 60 chars).
    Choose a short, specific <role> and the hiring <company>, e.g., 'resume_senior_data_engineer_acme'.
  - latex_body: the COMPLETE LaTeX document to compile.
- Use basic LaTeX; avoid custom packages/macros beyond essentials.
- Sections: Summary, Skills, Experience (impact bullets), Projects (optional), Education, Certifications (optional).
- Target exactly ONE page. Compress bullets, merge similar roles, abbreviate tech names, and remove low-value items if needed.
- In Skills, include only hard/technical skills, tools, stacks, platforms, and certs. Do NOT include soft skills (e.g., communication, teamwork, leadership).
- Bold key hard skills/terms that directly match the job description; avoid bolding soft skills or generic phrases.

Candidate resume (LaTeX):
{resume}

Job description:
{jd}

Company brief:
{brief}
"""


def _read_optional(path: Path) -> Optional[str]:
    """Read file if it exists; return None if not."""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("Failed to read %s: %s", path, e)
    return None

def _get_system_prompt() -> str:
    return _read_optional(PROMPTS_DIR / "system.txt") or DEFAULT_SYSTEM_PROMPT

def _get_user_template() -> str:
    return _read_optional(PROMPTS_DIR / "user.txt") or DEFAULT_USER_TEMPLATE

def _slugify(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")
# -----------------------------
# PDF compilation
# -----------------------------
def _detect_pdf_tool() -> Tuple[str, List[str]]:
    if shutil.which("latexmk"):
        return "latexmk", ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-f"]
    if shutil.which("pdflatex"):
        return "pdflatex", ["pdflatex", "-interaction=nonstopmode", "-halt-on-error"]
    if shutil.which("pandoc"):
        return "pandoc", ["pandoc"]
    return "", []

def _compile_pdf(tex_path: str) -> Tuple[bool, str, str]:
    """Compile TEX -> PDF in-place."""
    tex_file = Path(tex_path)
    workdir = tex_file.parent
    pdf_path = workdir / (tex_file.stem + ".pdf")

    tool, base_cmd = _detect_pdf_tool()
    if not tool:
        return (False, str(pdf_path), "No LaTeX tool found. Install MiKTeX/TeX Live or Pandoc.")

    if tool == "latexmk":
        cmd = base_cmd + [tex_file.name]
    elif tool == "pdflatex":
        cmd = base_cmd + [tex_file.name]
    elif tool == "pandoc":
        cmd = ["pandoc", tex_file.name, "-o", pdf_path.name]
    else:
        return (False, str(pdf_path), "Unknown LaTeX tool")

    log.info("Compiling PDF with %s: %s (cwd=%s)", tool, " ".join(cmd), workdir)
    try:
        p1 = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
        build_log = (p1.stdout or "") + "\n" + (p1.stderr or "")
        if tool == "pdflatex":
            p2 = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
            build_log += "\n(second pass)\n" + (p2.stdout or "") + "\n" + (p2.stderr or "")
            rc = p1.returncode or p2.returncode
        else:
            rc = p1.returncode
        ok = (rc == 0) and pdf_path.exists()
        return (ok, str(pdf_path), build_log)
    except Exception as e:
        return (False, str(pdf_path), f"Exception: {e}")

# -----------------------------
# MCP Server
# -----------------------------
mcp = FastMCP("resume-mcp")

# -----------------------------
# Resources (for Claude to read data)
# -----------------------------
@mcp.resource("resume://base")
def get_base_resume():
    """Get the current base resume LaTeX content."""
    if not STATE["resume_latex"]:
        return "No base resume loaded. Use load_resume() tool first."
    return STATE["resume_latex"]

@mcp.resource("job://description")
def get_job_description():
    """Get the current job description."""
    if not STATE["job_description"]:
        return "No job description loaded. Use load_job_posting() tool first."
    return STATE["job_description"]

@mcp.resource("company://brief")
def get_company_brief():
    """Get company research brief."""
    if not STATE["company_brief"]:
        company_name = STATE.get("company", "the company")
        return f"No company brief provided for {company_name}."
    return STATE["company_brief"]

@mcp.resource("prompts://system")
def get_system_prompt():
    """Get the system prompt template (customizable via data/prompts/system.txt)."""
    return _get_system_prompt()

@mcp.resource("prompts://user-template")
def get_user_template():
    """Get the user prompt template (customizable via data/prompts/user.txt)."""
    return _get_user_template()

@mcp.resource("prompts://complete")
def get_complete_prompt():
    """Get the complete, ready-to-use prompt for Claude."""
    if not STATE.get("resume_latex") or not STATE.get("job_description"):
        return "Error: Missing resume or job description. Load both first."
    
    system = _get_system_prompt()
    user_tpl = _get_user_template()
    brief = STATE.get("company_brief") or f"No company brief provided for {STATE.get('company', 'this company')}."
    
    user = user_tpl.format(
        resume=STATE["resume_latex"],
        jd=STATE["job_description"],
        brief=brief
    )
    
    return f"SYSTEM PROMPT:\n{system}\n\n" + "="*50 + f"\n\nUSER PROMPT:\n{user}"

# -----------------------------
# Tools (for Claude to take actions)
# -----------------------------
@mcp.tool()
def load_resume(latex: str) -> dict[str, str]:
    """Load the base resume in LaTeX format."""
    STATE["resume_latex"] = latex
    saved_path = _save_text("resume_base.tex", latex)
    return {
        "status": "loaded",
        "saved_to": saved_path,
        "length": str(len(latex))
    }

@mcp.tool()
def load_job_posting(description: str, company_name: Optional[str] = None) -> dict[str, Optional[str]]:
    """Load job description and optionally set company name."""
    STATE["job_description"] = description
    if company_name:
        STATE["company"] = company_name
    saved_path = _save_text("job_description.txt", description)
    return {
        "status": "loaded",
        "saved_to": saved_path,
        "company": company_name
    }

@mcp.tool()
def add_company_research(brief: str) -> dict[str, str]:
    """Add company research/brief to inform resume tailoring."""
    STATE["company_brief"] = brief
    saved_path = _save_text("company_brief.txt", brief)
    return {
        "status": "added",
        "saved_to": saved_path,
        "length": str(len(brief))
    }

@mcp.tool()
def get_workflow_status() -> ResumeStatus:
    """Get current status of the resume tailoring workflow."""
    return ResumeStatus(
        has_resume=STATE["resume_latex"] is not None,
        has_job_description=STATE["job_description"] is not None,
        company=STATE.get("company"),
        has_company_brief=STATE["company_brief"] is not None,
        ready_for_generation=(
            STATE["resume_latex"] is not None and 
            STATE["job_description"] is not None
        )
    )

@mcp.tool()
def submit_tailored_resume(filename_stem: str, latex_body: str) -> CompilationResult:
    """
    Structured output path: Claude calls this with a safe filename stem and the full LaTeX body.
    We save it as <stem>.tex and compile to PDF. Returns a CompilationResult.
    """
    if not latex_body or not latex_body.strip():
        return CompilationResult(
            success=False,
            pdf_path=None,
            tex_path="",
            error_message="Empty LaTeX body provided"
        )

    stem = _slugify(filename_stem or "")
    if not stem:
        # Fallback to resume_<company>
        company = STATE.get("company") or "company"
        stem = f"resume_{_slugify(company)}"
    # Ensure it starts with 'resume_'
    if not stem.startswith("resume_"):
        stem = f"resume_{stem}"
    # Enforce max length (keep filesystems happy)
    stem = stem[:60].rstrip("_") or "resume"

    # Avoid overwriting existing files; append timestamp if needed
    candidate_tex = DATA_DIR / f"{stem}.tex"
    if candidate_tex.exists():
        stem = f"{stem}_{_now_ts()}"

    # Save LaTeX and compile
    tex_path = _save_text(f"{stem}.tex", latex_body.strip())
    success, pdf_path, build_log = _compile_pdf(tex_path)

    return CompilationResult(
        success=success,
        pdf_path=pdf_path if success else None,
        tex_path=tex_path,
        error_message=None if success else (build_log[-1000:] if build_log else "Unknown LaTeX error")
    )

@mcp.tool()
def reset_workflow() -> dict[str, str]:
    """Clear all loaded data and start fresh."""
    for key in ["resume_latex", "job_description", "company", "company_brief"]:
        STATE[key] = None
    return {"status": "reset", "message": "All data cleared"}

if __name__ == "__main__":
    mcp.run(transport="stdio")