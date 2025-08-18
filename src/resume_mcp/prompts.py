"""
Prompt template management for resume and cover letter generation.
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import UserInfo
from .storage import get_prompts_dir

# Default prompts
DEFAULT_SYSTEM_PROMPT = (
    "You are an expert resume and cover letter specialist for Applicant Tracking Systems (ATS). "
    "Your role includes: (1) Tailoring LaTeX resumes to align with job descriptions and company context, "
    "and (2) Creating compelling cover letters when requested. "
    "Focus on ATS compatibility, keyword optimization, and professional presentation. "
    "Always use structured LaTeX output that compiles cleanly."
)

DEFAULT_USER_TEMPLATE = """Please tailor this resume for the job posting below, incorporating relevant company context.

**BASE RESUME:**
{resume}

**JOB DESCRIPTION:**
{jd}

**COMPANY CONTEXT:**
{brief}

**REQUIREMENTS:**
1. **ATS-Optimized:** Use standard LaTeX packages, avoid custom macros, maintain clean structure
2. **Keyword Matching:** Naturally incorporate relevant keywords from the job description
3. **Relevance Focus:** Emphasize experiences and skills most relevant to this specific role
4. **Quantified Impact:** Include metrics and achievements where possible using action verbs
5. **Professional Formatting:** Clean, readable layout that works across systems
6. **Length Target:** Aim for one page while including essential information
7. **Experience (impact bullets):** Show results and value delivered in each role

**OUTPUT:** Provide only the complete, tailored LaTeX resume code ready for compilation."""


def get_system_prompt() -> str:
    """Get the system prompt, checking for custom version first."""
    custom_prompt_path = get_prompts_dir() / "system.txt"
    
    if custom_prompt_path.exists():
        try:
            return custom_prompt_path.read_text(encoding='utf-8').strip()
        except Exception:
            pass  # Fall back to default if custom file has issues
    
    return DEFAULT_SYSTEM_PROMPT


def get_user_template() -> str:
    """Get the user prompt template, checking for custom version first."""
    custom_template_path = get_prompts_dir() / "user.txt"
    
    if custom_template_path.exists():
        try:
            content = custom_template_path.read_text(encoding='utf-8').strip()
            # Validate that required placeholders exist
            if '{resume}' in content and '{jd}' in content and '{brief}' in content:
                return content
        except Exception:
            pass  # Fall back to default if custom file has issues
    
    return DEFAULT_USER_TEMPLATE


def create_cover_letter_template_markdown(user_info: UserInfo, company: str, position: str) -> str:
    """Create a professional cover letter Markdown template."""
    contact_parts = [user_info.email]
    if user_info.phone:
        contact_parts.append(user_info.phone)
    if user_info.linkedin:
        contact_parts.append(user_info.linkedin)
    
    contact_line = " | ".join(contact_parts)
    address_line = user_info.address or "[Your Address]"
    today = datetime.now().strftime("%B %d, %Y")
    
    return f"""# {user_info.full_name}

{contact_line}  
{address_line}

---

{today}

Hiring Manager  
{company}

Dear Hiring Manager,

{{COVER_LETTER_BODY}}

Sincerely,

{user_info.full_name}
"""


def create_cover_letter_template_latex(user_info: UserInfo, company: str, position: str) -> str:
    """Create a professional cover letter LaTeX template."""
    contact_parts = [user_info.email]
    if user_info.phone:
        contact_parts.append(user_info.phone)
    if user_info.linkedin:
        contact_parts.append(user_info.linkedin)
    
    contact_line = " | ".join(contact_parts)
    address_line = user_info.address or "[Your Address]"
    today = datetime.now().strftime("%B %d, %Y")
    
    return f"""\\documentclass[letterpaper,11pt]{{article}}
\\usepackage[left=1in,top=1in,right=1in,bottom=1in]{{geometry}}
\\usepackage{{enumitem}}
\\usepackage{{titlesec}}

\\begin{{document}}

\\begin{{center}}
\\textbf{{\\Large {user_info.full_name}}}\\\\
\\vspace{{2pt}}
{contact_line}\\\\
{address_line}
\\end{{center}}

\\vspace{{20pt}}

{today}

\\vspace{{10pt}}

Hiring Manager\\\\
{company}

\\vspace{{10pt}}

Dear Hiring Manager,

{{COVER_LETTER_BODY}}

\\vspace{{10pt}}

Sincerely,

\\vspace{{20pt}}

{user_info.full_name}

\\end{{document}}
"""


def format_complete_prompt(resume_latex: str, job_description: str, company_brief: Optional[str] = None) -> str:
    """Format the complete prompt with all components."""
    if not resume_latex or not job_description:
        return "Error: Missing resume or job description. Load both first."
    
    system = get_system_prompt()
    user_tpl = get_user_template()
    brief = company_brief or "No company brief provided for this company."
    
    user = user_tpl.format(
        resume=resume_latex,
        jd=job_description,
        brief=brief
    )
    
    return f"SYSTEM PROMPT:\n{system}\n\n" + "="*50 + f"\n\nUSER PROMPT:\n{user}"