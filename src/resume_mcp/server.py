"""
Improved Resume MCP Server using resources and structured output.
"""
import sys
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Callable
from pydantic import BaseModel, Field
import re
import requests
import json
import threading
import time
import tempfile
import urllib.parse
import os
from mcp.server.fastmcp import FastMCP
# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("resume-mcp")

# Check for optional conversion libraries
try:
    import pypandoc
    import docx
    from docx.shared import Inches
    CONVERSION_AVAILABLE = True
except ImportError as e:
    log.warning(f"Document conversion libraries not available: {e}")
    CONVERSION_AVAILABLE = False

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
    "latex_warmed_up": False,
    "warmup_in_progress": False,
    # Cover letter state
    "user_info": None,  # User's personal info for cover letters
    "cover_letter_requested": None,  # Boolean - user wants cover letter
    "cover_letter_markdown": None,  # Generated cover letter (markdown format)
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
    download_prompt: Optional[str] = Field(description="User-friendly download prompt message")

class SearchResult(BaseModel):
    """Result of company web search."""
    success: bool = Field(description="Whether search was successful")
    company_info: Optional[str] = Field(description="Extracted company information")
    sources: List[str] = Field(description="URLs of sources used")
    error_message: Optional[str] = Field(description="Error message if search failed")

class UserInfo(BaseModel):
    """User's personal information for cover letters."""
    full_name: str = Field(description="User's full name")
    email: str = Field(description="User's email address")
    phone: Optional[str] = Field(description="User's phone number")
    address: Optional[str] = Field(description="User's address (city, state)")
    linkedin: Optional[str] = Field(description="LinkedIn profile URL")
    website: Optional[str] = Field(description="Personal website URL")

class CoverLetterRequest(BaseModel):
    """Request for cover letter generation."""
    wants_cover_letter: bool = Field(description="Whether user wants a cover letter generated")
    tone: Optional[str] = Field(description="Desired tone: professional, enthusiastic, formal, etc.")
    key_points: Optional[List[str]] = Field(description="Key points to emphasize in cover letter")
    closing_type: Optional[str] = Field(description="Closing style: standard, confident, humble, etc.")

class WorkflowStatus(BaseModel):
    """Extended status including cover letter workflow."""
    has_resume: bool = Field(description="Whether base resume is loaded")
    has_job_description: bool = Field(description="Whether job description is loaded")
    company: Optional[str] = Field(description="Company name if set")
    has_company_brief: bool = Field(description="Whether company research is available")
    has_user_info: bool = Field(description="Whether user info is loaded for cover letters")
    cover_letter_requested: Optional[bool] = Field(description="Whether user wants cover letter")
    has_cover_letter: bool = Field(description="Whether cover letter is generated")
    ready_for_generation: bool = Field(description="Whether ready to generate tailored resume")
    ready_for_cover_letter: bool = Field(description="Whether ready to generate cover letter")

class ConversionResult(BaseModel):
    """Result of document format conversion."""
    success: bool = Field(description="Whether conversion succeeded")
    output_path: Optional[str] = Field(description="Path to converted document")
    format: str = Field(description="Output format (docx, pdf, etc.)")
    error_message: Optional[str] = Field(description="Error message if conversion failed")

class CompilationProgress(BaseModel):
    """Progress tracking for LaTeX compilation."""
    stage: str = Field(description="Current compilation stage")
    progress: float = Field(description="Progress percentage (0-100)")
    message: str = Field(description="Progress message")
    eta_seconds: Optional[float] = Field(description="Estimated time remaining in seconds")
    
class ProgressCallback:
    """Progress tracking callback for LaTeX compilation."""
    
    def __init__(self, callback_fn: Optional[Callable[[CompilationProgress], None]] = None, 
                 use_terminal: bool = True, terminal_title: str = "LaTeX Compilation Progress"):
        self.callback_fn = callback_fn or self._default_progress_log
        self.start_time = time.time()
        self.current_stage = "initializing"
        self.progress_terminal = None
        
        # Start progress terminal if requested
        if use_terminal:
            self.progress_terminal = ProgressTerminal(terminal_title)
            self.progress_terminal._start_time = self.start_time
            if not self.progress_terminal.start():
                self.progress_terminal = None
        
    def _default_progress_log(self, progress: CompilationProgress):
        """Default progress logging to stderr and terminal."""
        elapsed = time.time() - self.start_time
        eta_msg = f" (ETA: {progress.eta_seconds:.1f}s)" if progress.eta_seconds else ""
        log_msg = f"[{elapsed:.1f}s] {progress.stage}: {progress.progress:.1f}% - {progress.message}{eta_msg}"
        
        # Log to stderr
        log.info(log_msg)
        
        # Also send to progress terminal if available
        if self.progress_terminal:
            self.progress_terminal.update_progress(
                progress.stage, progress.progress, progress.message, progress.eta_seconds
            )
    
    def update(self, stage: str, progress: float, message: str, eta_seconds: Optional[float] = None):
        """Update compilation progress."""
        self.current_stage = stage
        progress_obj = CompilationProgress(
            stage=stage,
            progress=progress,
            message=message,
            eta_seconds=eta_seconds
        )
        self.callback_fn(progress_obj)
    
    def log_stage(self, stage: str, message: str = ""):
        """Log a new stage at 0% progress."""
        self.update(stage, 0.0, message or f"Starting {stage}")
    
    def complete_stage(self, stage: str, message: str = ""):
        """Mark a stage as 100% complete."""
        self.update(stage, 100.0, message or f"Completed {stage}")
    
    def close_terminal(self):
        """Close the progress terminal if it exists."""
        if self.progress_terminal:
            self.progress_terminal.close()
            self.progress_terminal = None

# -----------------------------
# Prompt defaults
# -----------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are an expert resume and cover letter specialist for Applicant Tracking Systems (ATS). "
    "Your role includes: (1) Tailoring LaTeX resumes to align with job descriptions and company context, "
    "and (2) Creating compelling cover letters when requested. "
    
    "For resumes: Keep outputs ATS-friendly (minimal packages/macros), concise, factually accurate, and impact-focused. "
    "Target exactly one page whenever possible. "
    
    "For cover letters: Create personalized, professional letters that complement the resume by highlighting "
    "specific achievements and demonstrating company knowledge. Use the markdown cover letter template structure. "
    "Cover letters are automatically generated in Word (.docx) format and optionally PDF - the Word format "
    "is recommended for uploading to job portals and ATS systems. "
    
    "Workflow: (1) Check if user info is loaded for cover letters, (2) Generate resume with submit_tailored_resume(), "
    "(3) Generate cover letter with submit_cover_letter() if requested. Use export_document() to convert "
    "resumes to Word format if needed for uploading."
)

DEFAULT_USER_TEMPLATE = """Task:
- Read the candidate's current LaTeX resume and the job description.
- Use the company brief (if present) for terminology and emphasis.
- Produce an updated ATS-friendly LaTeX resume tailored to the role.

Output rules:
- Do NOT print the LaTeX directly. When finished, call 'submit_tailored_resume' with:
  - filename_stem: lower_snake_case like 'resume_<role>_<company>' (only [a-z0-9_], under 60 chars).
  - latex_body: the COMPLETE LaTeX document to compile.
- Use basic LaTeX; avoid custom packages/macros beyond essentials.
- Sections: Summary, Skills, Experience (impact bullets), Projects (optional), Education, Certifications (optional).
- Target exactly ONE page. Compress bullets, merge similar roles, abbreviate tech names, and remove low-value items if needed.
- Bold key hard skills/terms that directly match the job description.

Cover Letter Workflow:
1. Check coverletter://status resource for current status
2. If user info not loaded, suggest using load_user_info() tool
3. If cover letter preference not set, call elicit_cover_letter_preference() tool
4. If cover letter requested, call submit_cover_letter() with:
   - filename_stem: 'cover_letter_<role>_<company>'
   - cover_letter_body: 3-4 paragraphs of compelling, personalized content (markdown format)

Cover Letter Content Guidelines:
- Paragraph 1: Hook + specific position interest + brief value proposition
- Paragraph 2: 2-3 relevant achievements with quantified impact
- Paragraph 3: Company knowledge + how you'll add value + cultural fit
- Paragraph 4: Call to action + professional closing
- Use specific examples from resume, company research, and job requirements
- Match tone to company culture (formal/startup/etc.)

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
# System Notifications
# -----------------------------
def send_system_notification(title: str, message: str, duration: int = 5000) -> bool:
    """Send a system notification across platforms."""
    try:
        import platform
        system = platform.system().lower()
        
        if system == 'windows':
            try:
                # Try win10toast first
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=duration//1000, threaded=True)
                return True
            except ImportError:
                # Fallback to Windows native
                import subprocess
                subprocess.run([
                    'powershell', '-Command',
                    f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{title}")); $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{message}")); $toast = [Windows.UI.Notifications.ToastNotification]::new($template); [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Resume MCP").Show($toast)'
                ], capture_output=True, timeout=5)
                return True
                
        elif system == 'darwin':  # macOS
            import subprocess
            script = f'''display notification "{message}" with title "{title}"'''
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=5)
            return True
            
        else:  # Linux
            import subprocess
            subprocess.run(['notify-send', title, message], capture_output=True, timeout=5)
            return True
            
    except Exception as e:
        log.warning(f"Failed to send notification: {e}")
        return False

# -----------------------------
# Progress Terminal Management
# -----------------------------
class ProgressTerminal:
    """Manages a separate terminal window for displaying compilation progress."""
    
    def __init__(self, title: str = "LaTeX Compilation Progress"):
        self.title = title
        self.terminal_process = None
        self.temp_script = None
        self.progress_file = None
        self.is_active = False
        
    def start(self) -> bool:
        """Start a new terminal window for progress display."""
        try:
            import platform
            system = platform.system().lower()
            
            # Create a temporary file for progress updates
            self.progress_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False
            )
            self.progress_file.write(f"{self.title}\n")
            self.progress_file.write("=" * 50 + "\n")
            self.progress_file.write("Initializing LaTeX compilation...\n")
            self.progress_file.flush()
            progress_file_path = self.progress_file.name
            
            # Create a script that monitors the progress file
            self.temp_script = tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.bat' if system == 'windows' else '.sh',
                delete=False
            )
            
            if system == 'windows':
                # Windows batch script that monitors progress file
                script_content = f'''@echo off
title {self.title}
cls
:loop
cls
type "{progress_file_path}"
timeout /t 1 /nobreak >nul
if exist "{progress_file_path}" goto loop
echo.
echo Compilation finished. Press any key to close...
pause >nul
'''
                self.temp_script.write(script_content)
                self.temp_script.close()
                
                # Start new cmd window
                self.terminal_process = subprocess.Popen([
                    'cmd', '/c', 'start', 'cmd', '/c', self.temp_script.name
                ], shell=True)
                
            elif system == 'darwin':  # macOS
                # macOS shell script that monitors progress file
                script_content = f'''#!/bin/bash
while [ -f "{progress_file_path}" ]; do
    clear
    cat "{progress_file_path}"
    sleep 1
done
echo ""
echo "Compilation finished. Press any key to close..."
read -n 1
'''
                self.temp_script.write(script_content)
                self.temp_script.close()
                os.chmod(self.temp_script.name, 0o755)
                
                # Start new Terminal window
                self.terminal_process = subprocess.Popen([
                    'osascript', '-e', 
                    f'tell app "Terminal" to do script "bash {self.temp_script.name}"'
                ])
                
            else:  # Linux
                # Linux shell script that monitors progress file
                script_content = f'''#!/bin/bash
while [ -f "{progress_file_path}" ]; do
    clear
    cat "{progress_file_path}"
    sleep 1
done
echo ""
echo "Compilation finished. Press any key to close..."
read -n 1
'''
                self.temp_script.write(script_content)
                self.temp_script.close()
                os.chmod(self.temp_script.name, 0o755)
                
                # Try different terminal emulators
                terminals = ['gnome-terminal', 'konsole', 'xterm']
                for term in terminals:
                    if shutil.which(term):
                        if term == 'gnome-terminal':
                            self.terminal_process = subprocess.Popen([
                                term, '--', 'bash', self.temp_script.name
                            ])
                        else:
                            self.terminal_process = subprocess.Popen([
                                term, '-e', f'bash {self.temp_script.name}'
                            ])
                        break
                
            self.is_active = True
            log.info(f"Started progress terminal: {self.title}")
            return True
            
        except Exception as e:
            log.warning(f"Failed to start progress terminal: {e}")
            return False
    
    def update_progress(self, stage: str, progress: float, message: str, eta: Optional[float] = None):
        """Update the progress display by writing to the progress file."""
        if self.is_active and self.progress_file:
            try:
                elapsed = time.time() - getattr(self, '_start_time', time.time())
                eta_msg = f" (ETA: {eta:.1f}s)" if eta else ""
                
                # Create progress bar using ASCII characters
                bar_length = 40
                filled_length = int(bar_length * progress / 100)
                bar = '=' * filled_length + '-' * (bar_length - filled_length)
                
                # Write updated content to progress file
                with open(self.progress_file.name, 'w') as f:
                    f.write(f"{self.title}\n")
                    f.write("=" * 50 + "\n")
                    f.write(f"Stage: {stage.title()}\n")
                    f.write(f"Progress: [{bar}] {progress:.1f}%\n")
                    f.write(f"Status: {message}\n")
                    f.write(f"Elapsed: {elapsed:.1f}s{eta_msg}\n")
                    f.write("\n")
                    if progress >= 100:
                        f.write("COMPLETED\n")
                    f.flush()
                    
            except Exception as e:
                log.warning(f"Failed to update progress display: {e}")
    
    def close(self):
        """Close the progress terminal."""
        # Delete progress file to signal terminal to close
        if self.progress_file:
            try:
                os.unlink(self.progress_file.name)
            except:
                pass
            self.progress_file = None
        
        # Wait a moment for terminal to detect file deletion
        time.sleep(1)
        
        if self.terminal_process:
            try:
                self.terminal_process.terminate()
            except:
                pass
        
        if self.temp_script and os.path.exists(self.temp_script.name):
            try:
                os.unlink(self.temp_script.name)
            except:
                pass
        
        self.is_active = False
        log.info("Closed progress terminal")

# -----------------------------
# Directory Management
# -----------------------------
def clear_data_directory(keep_latest_pdf: bool = True, keep_latest_docx: bool = True) -> Tuple[bool, str]:
    """Clear data directory while optionally keeping latest PDF and DOCX files.
    
    Args:
        keep_latest_pdf: If True, keeps the most recently modified PDF file
        keep_latest_docx: If True, keeps the most recently modified DOCX file
        
    Returns:
        Tuple of (success, message)
    """
    try:
        if not DATA_DIR.exists():
            return True, "Data directory does not exist"
        
        # Get all files in data directory
        all_files = list(DATA_DIR.glob("*"))
        files_to_delete = []
        
        # Find latest PDF and DOCX if we need to keep them
        latest_pdf = None
        latest_docx = None
        
        if keep_latest_pdf:
            pdf_files = [f for f in all_files if f.suffix.lower() == '.pdf' and f.is_file()]
            if pdf_files:
                latest_pdf = max(pdf_files, key=lambda f: f.stat().st_mtime)
        
        if keep_latest_docx:
            docx_files = [f for f in all_files if f.suffix.lower() == '.docx' and f.is_file()]
            if docx_files:
                latest_docx = max(docx_files, key=lambda f: f.stat().st_mtime)
        
        # Determine which files to delete
        for file_path in all_files:
            if not file_path.is_file():
                continue  # Skip directories
            
            # Keep the latest PDF and DOCX files
            if file_path == latest_pdf or file_path == latest_docx:
                continue
                
            files_to_delete.append(file_path)
        
        # Delete the files
        deleted_count = 0
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted_count += 1
                log.info(f"Deleted: {file_path.name}")
            except Exception as e:
                log.warning(f"Failed to delete {file_path.name}: {e}")
        
        # Prepare summary message
        kept_files = []
        if latest_pdf and latest_pdf.exists():
            kept_files.append(f"PDF: {latest_pdf.name}")
        if latest_docx and latest_docx.exists():
            kept_files.append(f"DOCX: {latest_docx.name}")
        
        kept_msg = f"Kept files: {', '.join(kept_files)}" if kept_files else "No files kept"
        message = f"Cleared data directory. Deleted {deleted_count} files. {kept_msg}"
        
        return True, message
        
    except Exception as e:
        error_msg = f"Error clearing data directory: {str(e)}"
        log.error(error_msg)
        return False, error_msg

# -----------------------------
# PDF compilation
# -----------------------------
def _detect_pdf_tool() -> Tuple[str, List[str]]:
    # Check for latexmk
    latexmk_path = shutil.which("latexmk")
    if latexmk_path:
        log.info(f"Found latexmk at: {latexmk_path}")
        return "latexmk", ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-f"]
    
    # Check for pdflatex
    pdflatex_path = shutil.which("pdflatex")
    if pdflatex_path:
        log.info(f"Found pdflatex at: {pdflatex_path}")
        return "pdflatex", ["pdflatex", "-interaction=nonstopmode", "-halt-on-error"]
    
    # Check for pandoc
    pandoc_path = shutil.which("pandoc")
    if pandoc_path:
        log.info(f"Found pandoc at: {pandoc_path}")
        return "pandoc", ["pandoc"]
    
    # Log what's in PATH for debugging
    import os
    path_dirs = os.environ.get('PATH', '').split(os.pathsep)
    miktex_dirs = [d for d in path_dirs if 'miktex' in d.lower() or 'tex' in d.lower()]
    if miktex_dirs:
        log.warning(f"Found TeX-related directories in PATH: {miktex_dirs}")
    else:
        log.warning("No TeX-related directories found in PATH")
    
    return "", []

def _compile_pdf(tex_path: str, progress_callback: Optional[ProgressCallback] = None) -> Tuple[bool, str, str]:
    """Compile TEX -> PDF in-place with optional progress tracking."""
    if progress_callback is None:
        progress_callback = ProgressCallback()
    
    tex_file = Path(tex_path)
    workdir = tex_file.parent
    pdf_path = workdir / (tex_file.stem + ".pdf")

    progress_callback.log_stage("detection", "Detecting LaTeX tools")
    
    tool, base_cmd = _detect_pdf_tool()
    if not tool:
        progress_callback.update("detection", 100.0, "No LaTeX tool found", 0.0)
        return (False, str(pdf_path), "No LaTeX tool found. Install MiKTeX/TeX Live or Pandoc.")

    progress_callback.update("detection", 100.0, f"Using {tool}")
    
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
        progress_callback.log_stage("compilation", f"Running {tool} (pass 1)")
        
        start_time = time.time()
        p1 = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
        first_pass_time = time.time() - start_time
        
        build_log = (p1.stdout or "") + "\n" + (p1.stderr or "")
        
        if tool == "pdflatex":
            progress_callback.update("compilation", 50.0, "Running pdflatex (pass 2)", first_pass_time)
            
            p2 = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
            build_log += "\n(second pass)\n" + (p2.stdout or "") + "\n" + (p2.stderr or "")
            rc = p1.returncode or p2.returncode
        else:
            rc = p1.returncode
        
        progress_callback.update("compilation", 90.0, "Checking output file")
        
        ok = (rc == 0) and pdf_path.exists()
        
        if ok:
            progress_callback.complete_stage("compilation", "PDF generated successfully")
        else:
            progress_callback.update("compilation", 100.0, "Compilation failed", 0.0)
            
        return (ok, str(pdf_path), build_log)
    except Exception as e:
        progress_callback.update("compilation", 100.0, f"Exception: {e}", 0.0)
        return (False, str(pdf_path), f"Exception: {e}")

# -----------------------------
# LaTeX Warmup Functions
# -----------------------------
def _create_warmup_latex() -> str:
    """Create a minimal LaTeX document to warm up the compilation tools."""
    return r"""
\documentclass[letterpaper,11pt]{article}
\usepackage[left=0.75in,top=0.6in,right=0.75in,bottom=0.6in]{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}

\titleformat{\section}{\large\bfseries\uppercase}{}{0em}{}[\titlerule]
\titlespacing{\section}{0pt}{8pt}{6pt}
\titleformat{\subsection}{\bfseries}{}{0em}{}
\titlespacing{\subsection}{0pt}{4pt}{4pt}

\setlist[itemize]{leftmargin=*,topsep=0pt,itemsep=0pt}

\begin{document}

\begin{center}
\textbf{\Large WARMUP TEST}\\
\vspace{2pt}
Email: test@example.com $|$ Phone: (555) 123-4567
\end{center}

\section{Experience}
\subsection{Test Position | Test Company \hfill Jan 2024 -- Present}
\begin{itemize}
\item This is a test bullet point to warm up LaTeX compilation
\item Testing common resume packages and formatting
\end{itemize}

\section{Skills}
\textbf{Technical:} Python, LaTeX, Resume Formatting

\end{document}
"""

def _create_cover_letter_template_markdown(user_info: UserInfo, company: str, position: str) -> str:
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


def _warmup_latex_async():
    """Warm up LaTeX tools in a background thread."""
    try:
        log.info("Starting LaTeX warmup process...")
        STATE["warmup_in_progress"] = True
        
        # Create warmup file
        warmup_tex = DATA_DIR / "warmup_test.tex"
        warmup_tex.write_text(_create_warmup_latex(), encoding="utf-8")
        
        # Try to compile the warmup document
        success, pdf_path, build_log = _compile_pdf(str(warmup_tex))
        
        if success:
            log.info("LaTeX warmup completed successfully")
            STATE["latex_warmed_up"] = True
            # Clean up warmup files
            try:
                warmup_tex.unlink(missing_ok=True)
                Path(pdf_path).unlink(missing_ok=True)
                # Clean up auxiliary files
                for ext in ['.aux', '.log', '.out', '.fls', '.fdb_latexmk']:
                    aux_file = DATA_DIR / f"warmup_test{ext}"
                    aux_file.unlink(missing_ok=True)
            except Exception as e:
                log.warning(f"Failed to clean warmup files: {e}")
        else:
            log.warning(f"LaTeX warmup failed: {build_log[-500:]}")
            
    except Exception as e:
        log.error(f"LaTeX warmup error: {e}")
    finally:
        STATE["warmup_in_progress"] = False

def _ensure_latex_warmed_up():
    """Ensure LaTeX is warmed up, starting warmup if needed."""
    if not STATE["latex_warmed_up"] and not STATE["warmup_in_progress"]:
        # Start warmup in background thread
        warmup_thread = threading.Thread(target=_warmup_latex_async, daemon=True)
        warmup_thread.start()

def _compile_pdf_with_progress(tex_path: str, progress_callback: Optional[ProgressCallback] = None) -> Tuple[bool, str, str]:
    """Compile PDF with progress feedback and warmup check."""
    if progress_callback is None:
        progress_callback = ProgressCallback()
    
    # Ensure LaTeX is warmed up
    if not STATE["latex_warmed_up"]:
        progress_callback.log_stage("warmup", "LaTeX not warmed up - initializing tools")
        _ensure_latex_warmed_up()
        
        # If warmup is in progress, wait a bit for it to complete
        if STATE["warmup_in_progress"]:
            progress_callback.update("warmup", 25.0, "Waiting for warmup to complete...")
            wait_count = 0
            while STATE["warmup_in_progress"] and wait_count < 30:  # Wait max 30 seconds
                time.sleep(1)
                wait_count += 1
                progress = min(25.0 + (wait_count / 30.0) * 50.0, 75.0)
                progress_callback.update("warmup", progress, f"Warming up LaTeX tools... ({wait_count}s)")
        
        if STATE["latex_warmed_up"]:
            progress_callback.complete_stage("warmup", "LaTeX tools ready")
        else:
            progress_callback.update("warmup", 100.0, "Warmup timeout - proceeding anyway")
    else:
        progress_callback.update("warmup", 100.0, "LaTeX tools already warmed up")
    
    return _compile_pdf(tex_path, progress_callback)

# -----------------------------
# Document Conversion Functions
# -----------------------------
def _convert_markdown_to_word(markdown_path: str, output_format: str = "docx") -> Tuple[bool, str, str]:
    """Convert Markdown document to Word format using pandoc."""
    if not CONVERSION_AVAILABLE:
        return False, "", "Document conversion libraries not installed"
    
    # Check if pandoc is available
    if not shutil.which("pandoc"):
        return False, "", "Pandoc not installed. Install from: https://pandoc.org/installing.html"
    
    markdown_file = Path(markdown_path)
    output_path = markdown_file.parent / f"{markdown_file.stem}.{output_format}"
    
    try:
        log.info(f"Converting {markdown_path} to {output_format} using pandoc")
        
        # Use pypandoc to convert Markdown to Word with better formatting
        output = pypandoc.convert_file(
            str(markdown_path), 
            output_format,
            outputfile=str(output_path),
            extra_args=[
                '--standalone',
                '--wrap=none'
            ]
        )
        
        if output_path.exists():
            return True, str(output_path), "Conversion successful"
        else:
            return False, str(output_path), "Output file not created"
            
    except Exception as e:
        log.error(f"Conversion failed: {e}")
        return False, str(output_path), f"Conversion error: {str(e)}"

def _convert_tex_to_word(tex_path: str, output_format: str = "docx") -> Tuple[bool, str, str]:
    """Convert LaTeX document to Word format using pandoc."""
    if not CONVERSION_AVAILABLE:
        return False, "", "Document conversion libraries not installed"
    
    # Check if pandoc is available
    if not shutil.which("pandoc"):
        return False, "", "Pandoc not installed. Install from: https://pandoc.org/installing.html"
    
    tex_file = Path(tex_path)
    output_path = tex_file.parent / f"{tex_file.stem}.{output_format}"
    
    try:
        log.info(f"Converting {tex_path} to {output_format} using pandoc")
        
        # Use pypandoc to convert LaTeX to Word
        output = pypandoc.convert_file(
            str(tex_path), 
            output_format,
            outputfile=str(output_path),
            extra_args=['--standalone']
        )
        
        if output_path.exists():
            return True, str(output_path), "Conversion successful"
        else:
            return False, str(output_path), "Output file not created"
            
    except Exception as e:
        log.error(f"Conversion failed: {e}")
        return False, str(output_path), f"Conversion error: {str(e)}"

def _detect_conversion_tools() -> dict:
    """Detect available document conversion tools."""
    tools = {
        "pandoc": shutil.which("pandoc") is not None,
        "python_docx": CONVERSION_AVAILABLE,
        "recommended_formats": []
    }
    
    if tools["pandoc"] and tools["python_docx"]:
        tools["recommended_formats"] = ["docx", "pdf"]
    elif tools["pandoc"]:
        tools["recommended_formats"] = ["docx"]
    
    return tools

# -----------------------------
# Web Search Functions
# -----------------------------
def _search_company_info(company_name: str) -> SearchResult:
    """Search for company information using web search APIs."""
    if not company_name or not company_name.strip():
        return SearchResult(
            success=False,
            company_info=None,
            sources=[],
            error_message="No company name provided"
        )
    
    try:
        # Use DuckDuckGo instant answer API or similar free service
        search_query = f"{company_name} company overview business model products services"
        
        # Simple web scraping approach using requests
        # Note: In production, consider using proper search APIs like Bing, Google Custom Search, etc.
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Try DuckDuckGo instant answers first
        ddg_url = f"https://api.duckduckgo.com/?q={company_name}&format=json&no_html=1&skip_disambig=1"
        response = requests.get(ddg_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            abstract = data.get('Abstract', '')
            if abstract:
                return SearchResult(
                    success=True,
                    company_info=f"Company Overview: {abstract}",
                    sources=[data.get('AbstractURL', 'DuckDuckGo')],
                    error_message=None
                )
        
        # Fallback: construct basic company info prompt
        basic_info = f"Company: {company_name}\nNote: Web search unavailable. Please manually research this company's business model, products/services, company culture, recent news, and key values to better tailor the resume."
        
        return SearchResult(
            success=True,
            company_info=basic_info,
            sources=[],
            error_message="Limited information available - manual research recommended"
        )
        
    except Exception as e:
        log.warning(f"Company search failed for {company_name}: {e}")
        return SearchResult(
            success=False,
            company_info=None,
            sources=[],
            error_message=f"Search error: {str(e)}"
        )

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

@mcp.resource("search://capabilities")
def get_search_capabilities():
    """Get information about available search functionality."""
    return """Web Search Capabilities:
    
Available Tools:
- search_company_info(company_name): Search for company information and automatically add to company_brief
- load_job_posting_with_research(description, company_name, auto_research=True): Load job and auto-research company

Search Sources:
- DuckDuckGo instant answers API (primary)
- Fallback to structured research prompts when APIs unavailable

Automatic Features:
- Company research is automatically saved to company_brief when found
- Search results are cached in data/ directory for reference
- Failed searches provide research guidance for manual lookup

Usage Notes:
- Company research enhances resume tailoring with business context
- Search is automatically triggered when using load_job_posting_with_research
- Manual search available via search_company_info tool"""

@mcp.resource("coverletter://template")
def get_cover_letter_template():
    """Get cover letter template structure for AI guidance."""
    if not STATE.get("user_info"):
        return "No user info loaded. Use load_user_info() tool to add personal information for cover letters."
    
    company = STATE.get("company", "[Company Name]")
    position = "[Position Title]"
    user_info = UserInfo.model_validate(STATE["user_info"])
    
    template = _create_cover_letter_template_markdown(user_info, company, position)
    return f"""Cover Letter Template Structure:

{template}

Instructions for AI:
- Replace {{COVER_LETTER_BODY}} with 3-4 compelling paragraphs in markdown format
- Paragraph 1: Hook + specific position interest
- Paragraph 2: Relevant experience and achievements
- Paragraph 3: Company knowledge + value proposition
- Paragraph 4: Call to action + closing

Guidelines:
- Keep to one page
- Use markdown formatting (bold for emphasis, etc.)
- Use specific examples from resume
- Match tone to company culture
- Include 2-3 key skills from job description
- Output will be automatically converted to Word format"""

@mcp.resource("coverletter://status")
def get_cover_letter_status():
    """Get current cover letter workflow status."""
    status = {
        "user_info_loaded": STATE.get("user_info") is not None,
        "cover_letter_requested": STATE.get("cover_letter_requested"),
        "cover_letter_generated": STATE.get("cover_letter_markdown") is not None,
        "requirements_met": STATE.get("user_info") is not None and STATE.get("job_description") is not None
    }
    
    if not status["user_info_loaded"]:
        status["next_step"] = "Load user info with load_user_info() tool"
    elif status["cover_letter_requested"] is None:
        status["next_step"] = "Ask user if they want a cover letter with elicit_cover_letter_preference() tool"
    elif status["cover_letter_requested"] and not status["cover_letter_generated"]:
        status["next_step"] = "Generate cover letter with submit_cover_letter() tool"
    else:
        status["next_step"] = "Ready to proceed"
    
    return f"Cover Letter Status: {status}"

@mcp.resource("conversion://capabilities")
def get_conversion_capabilities():
    """Get document conversion capabilities and recommendations."""
    tools = _detect_conversion_tools()
    return f"""Document Conversion Capabilities:

Available Tools:
- export_document(tex_file_path, output_format): Convert LaTeX to Word/PDF/HTML/TXT
- get_conversion_status(): Check conversion tool availability

Supported Formats:
- docx (Word) - Recommended for job portal uploads
- pdf - Standard format for viewing/printing  
- html - Web-friendly format
- txt - Plain text format

Current Status:
- Conversion Available: {CONVERSION_AVAILABLE}
- Pandoc Installed: {tools['pandoc']}
- Python-docx Available: {tools['python_docx']}
- Recommended Format: {tools.get('recommended_formats', ['pdf'])[0] if tools.get('recommended_formats') else 'pdf'}

Usage Recommendations:
- Cover letters: Automatically generated in Word format for easy uploading
- Resumes: Use export_document() to convert to Word for ATS systems
- PDF format: Best for direct email attachments and viewing
- Word format: Required by most job portals and ATS systems

Note: Cover letters generated with submit_cover_letter() automatically create both PDF and Word versions when conversion tools are available."""

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
def load_user_info(full_name: str, email: str, phone: str = None, address: str = None, linkedin: str = None, website: str = None) -> dict[str, str]:
    """Load user's personal information for cover letter generation."""
    user_info = UserInfo(
        full_name=full_name,
        email=email,
        phone=phone,
        address=address,
        linkedin=linkedin,
        website=website
    )
    STATE["user_info"] = user_info.model_dump()
    saved_path = _save_text("user_info.json", json.dumps(STATE["user_info"], indent=2))
    return {
        "status": "loaded",
        "saved_to": saved_path,
        "message": f"User info loaded for {full_name}"
    }

@mcp.tool()
def elicit_cover_letter_preference() -> dict[str, str]:
    """Interactive tool to ask user if they want a cover letter generated."""
    return {
        "prompt": "Would you like me to generate a cover letter along with your tailored resume?",
        "options": {
            "yes": "Generate both resume and cover letter",
            "no": "Only generate resume",
            "later": "Ask me again later"
        },
        "instruction": "Please respond with 'yes', 'no', or 'later'. Use set_cover_letter_preference() tool with your choice.",
        "benefits": "A tailored cover letter can significantly increase your application success rate by showing specific interest and fit for the role."
    }

@mcp.tool()
def set_cover_letter_preference(wants_cover_letter: bool, tone: str = "professional", key_points: List[str] = None, closing_type: str = "standard") -> dict[str, str]:
    """Set user's preference for cover letter generation."""
    STATE["cover_letter_requested"] = wants_cover_letter
    
    if wants_cover_letter:
        request = CoverLetterRequest(
            wants_cover_letter=True,
            tone=tone,
            key_points=key_points or [],
            closing_type=closing_type
        )
        STATE["cover_letter_request"] = request.model_dump()
        _save_text("cover_letter_request.json", json.dumps(STATE["cover_letter_request"], indent=2))
        return {
            "status": "set",
            "message": f"Cover letter requested with {tone} tone and {closing_type} closing"
        }
    else:
        return {
            "status": "declined", 
            "message": "Cover letter generation declined"
        }

@mcp.tool()
def get_workflow_status() -> WorkflowStatus:
    """Get current status of the resume and cover letter workflow."""
    return WorkflowStatus(
        has_resume=STATE["resume_latex"] is not None,
        has_job_description=STATE["job_description"] is not None,
        company=STATE.get("company"),
        has_company_brief=STATE["company_brief"] is not None,
        has_user_info=STATE.get("user_info") is not None,
        cover_letter_requested=STATE.get("cover_letter_requested"),
        has_cover_letter=STATE.get("cover_letter_markdown") is not None,
        ready_for_generation=(
            STATE["resume_latex"] is not None and 
            STATE["job_description"] is not None
        ),
        ready_for_cover_letter=(
            STATE.get("user_info") is not None and
            STATE["job_description"] is not None and
            STATE.get("cover_letter_requested") is True
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

    # Save LaTeX and compile with warmup support
    tex_path = _save_text(f"{stem}.tex", latex_body.strip())
    
    # Send start notification
    send_system_notification("LaTeX Compilation Started", f"Compiling resume: {stem}")
    
    # Create progress callback without terminal (notifications only)
    progress_callback = ProgressCallback(use_terminal=False)
    progress_callback.log_stage("initialization", f"Starting resume compilation for {stem}")
    
    success, pdf_path, build_log = _compile_pdf_with_progress(tex_path, progress_callback)
    
    # Send completion notification
    if success:
        progress_callback.complete_stage("finalization", "Resume compilation completed successfully")
        import os
        send_system_notification(
            "✓ Resume Ready!", 
            f"PDF generated successfully: {os.path.basename(pdf_path) if pdf_path else stem}.pdf"
        )
    else:
        progress_callback.update("finalization", 100.0, "Compilation failed - check logs", 0.0)
        send_system_notification(
            "✗ Compilation Failed", 
            f"LaTeX compilation failed for {stem}. Check the error details."
        )

    # Create download prompt if successful
    download_prompt = None
    if success and pdf_path:
        import os
        pdf_name = os.path.basename(pdf_path)
        tex_name = os.path.basename(tex_path)
        download_prompt = f"Resume generated successfully!\n\nFiles ready for download:\n• PDF: {pdf_name}\n• LaTeX: {tex_name}\n\nLocation: {DATA_DIR}\n\nThe PDF is ready for job applications!"

    return CompilationResult(
        success=success,
        pdf_path=pdf_path if success else None,
        tex_path=tex_path,
        error_message=None if success else (build_log[-1000:] if build_log else "Unknown LaTeX error"),
        download_prompt=download_prompt
    )

@mcp.tool()
def submit_cover_letter(filename_stem: str, cover_letter_body: str, auto_convert_to_word: bool = True) -> dict:
    """
    Generate cover letter from body content. The body should be 3-4 paragraphs 
    of markdown-formatted text that will be inserted into the template.
    Automatically converts to Word format for easy uploading to job portals.
    """
    if not STATE.get("user_info"):
        return {
            "success": False,
            "error": "User info not loaded. Use load_user_info() tool first."
        }
    
    if not cover_letter_body or not cover_letter_body.strip():
        return {
            "success": False,
            "error": "Empty cover letter body provided"
        }

    user_info = UserInfo.model_validate(STATE["user_info"])
    company = STATE.get("company", "Company")
    position = "Position"  # Could be extracted from job description
    
    # Create full markdown document
    template = _create_cover_letter_template_markdown(user_info, company, position)
    full_markdown = template.replace("{COVER_LETTER_BODY}", cover_letter_body.strip())
    
    # Generate filename
    stem = _slugify(filename_stem or f"cover_letter_{company}")
    if not stem.startswith("cover_letter_"):
        stem = f"cover_letter_{stem}"
    stem = stem[:60].rstrip("_") or "cover_letter"

    # Avoid overwriting existing files
    candidate_md = DATA_DIR / f"{stem}.md"
    if candidate_md.exists():
        stem = f"{stem}_{_now_ts()}"

    # Save markdown
    md_path = _save_text(f"{stem}.md", full_markdown)
    STATE["cover_letter_markdown"] = full_markdown
    
    result = {
        "md_path": md_path,
        "formats_generated": []
    }
    
    # Auto-convert to Word if requested and available (primary format)
    if auto_convert_to_word and CONVERSION_AVAILABLE:
        word_success, word_path, word_message = _convert_markdown_to_word(md_path, "docx")
        if word_success:
            result["formats_generated"].append({"format": "docx", "path": word_path})
            result["recommended_upload"] = word_path
        else:
            result["word_conversion_error"] = word_message
    
    # Optionally generate PDF via pandoc
    if CONVERSION_AVAILABLE:
        pdf_success, pdf_path, pdf_message = _convert_markdown_to_word(md_path, "pdf")
        if pdf_success:
            result["formats_generated"].append({"format": "pdf", "path": pdf_path})
    
    result["success"] = len(result["formats_generated"]) > 0
    if not result["success"]:
        error_msg = result.get("word_conversion_error", "Generation failed")
        result["error"] = error_msg
    else:
        # Create download prompt
        import os
        download_prompt = "Cover letter generated successfully!\n\nFiles ready for download:\n"
        
        for format_info in result["formats_generated"]:
            file_name = os.path.basename(format_info["path"])
            format_type = format_info["format"].upper()
            download_prompt += f"• {format_type}: {file_name}\n"
        
        download_prompt += f"\nLocation: {DATA_DIR}\n"
        
        if "recommended_upload" in result:
            rec_file = os.path.basename(result["recommended_upload"])
            download_prompt += f"\nRecommended for job portals: {rec_file}"
        
        result["download_prompt"] = download_prompt
        result["message"] = f"Cover letter generated in {len(result['formats_generated'])} format(s)"
        if "recommended_upload" in result:
            result["message"] += f". Upload {result['recommended_upload']} to job portals."
    
    return result

@mcp.tool()
def search_company_info(company_name: str) -> SearchResult:
    """Search the web for company information to aid in resume tailoring."""
    search_result = _search_company_info(company_name)
    
    # If search was successful, automatically add the info to company_brief
    if search_result.success and search_result.company_info:
        STATE["company_brief"] = search_result.company_info
        _save_text(f"company_brief_{_slugify(company_name)}.txt", search_result.company_info)
        log.info(f"Automatically added company research for {company_name}")
    
    return search_result

@mcp.tool()
def load_job_posting_with_research(description: str, company_name: str, auto_research: bool = True) -> dict:
    """Load job description and automatically research the company if requested."""
    # Load the job posting first
    job_result = load_job_posting(description, company_name)
    
    result = {
        "job_status": job_result,
        "company_research": None
    }
    
    # Automatically research company if requested
    if auto_research and company_name:
        log.info(f"Auto-researching company: {company_name}")
        search_result = _search_company_info(company_name)
        
        if search_result.success and search_result.company_info:
            STATE["company_brief"] = search_result.company_info
            _save_text(f"company_brief_{_slugify(company_name)}.txt", search_result.company_info)
            result["company_research"] = {
                "status": "success",
                "info_length": len(search_result.company_info),
                "sources": search_result.sources
            }
        else:
            result["company_research"] = {
                "status": "failed", 
                "error": search_result.error_message
            }
    
    return result

@mcp.tool()
def warmup_latex() -> dict[str, str]:
    """Manually trigger LaTeX warmup to speed up future compilations."""
    if STATE["latex_warmed_up"]:
        return {"status": "already_warmed", "message": "LaTeX tools are already warmed up"}
    
    if STATE["warmup_in_progress"]:
        return {"status": "in_progress", "message": "LaTeX warmup is already in progress"}
    
    _ensure_latex_warmed_up()
    return {"status": "started", "message": "LaTeX warmup started in background"}

@mcp.tool()
def get_compilation_status() -> dict:
    """Get status of LaTeX compilation system."""
    tool, _ = _detect_pdf_tool()
    return {
        "latex_tool": tool or "none",
        "latex_warmed_up": STATE["latex_warmed_up"],
        "warmup_in_progress": STATE["warmup_in_progress"],
        "recommendation": "Run warmup_latex() to speed up compilations" if not STATE["latex_warmed_up"] else "Ready for fast compilation"
    }

@mcp.tool()
def export_document(tex_file_path: str, output_format: str = "docx") -> ConversionResult:
    """
    Convert a LaTeX document to Word (.docx) or other formats for easy uploading.
    Recommended for cover letters and resumes for job portals.
    """
    if not CONVERSION_AVAILABLE:
        return ConversionResult(
            success=False,
            output_path=None,
            format=output_format,
            error_message="Conversion libraries not installed. Run: uv sync"
        )
    
    if not Path(tex_file_path).exists():
        return ConversionResult(
            success=False,
            output_path=None,
            format=output_format,
            error_message=f"LaTeX file not found: {tex_file_path}"
        )
    
    supported_formats = ["docx", "pdf", "html", "txt"]
    if output_format not in supported_formats:
        return ConversionResult(
            success=False,
            output_path=None,
            format=output_format,
            error_message=f"Unsupported format. Use: {', '.join(supported_formats)}"
        )
    
    if output_format == "pdf":
        # Use existing PDF compilation
        success, pdf_path, build_log = _compile_pdf_with_progress(tex_file_path)
        return ConversionResult(
            success=success,
            output_path=pdf_path if success else None,
            format="pdf",
            error_message=None if success else build_log[-500:]
        )
    else:
        # Use pandoc for other formats
        success, output_path, message = _convert_tex_to_word(tex_file_path, output_format)
        return ConversionResult(
            success=success,
            output_path=output_path if success else None,
            format=output_format,
            error_message=None if success else message
        )

@mcp.tool()
def get_conversion_status() -> dict:
    """Get status of document conversion capabilities."""
    tools = _detect_conversion_tools()
    return {
        "conversion_available": CONVERSION_AVAILABLE,
        "pandoc_installed": tools["pandoc"],
        "python_docx_available": tools["python_docx"],
        "supported_formats": ["docx", "pdf", "html", "txt"] if CONVERSION_AVAILABLE else [],
        "recommended_format": "docx" if tools["pandoc"] else "pdf",
        "recommendation": "Use docx format for easy uploading to job portals" if tools["pandoc"] else "Install pandoc for Word conversion"
    }

@mcp.tool()
def send_progress_notification(stage: str, progress: float, message: str, eta_seconds: Optional[float] = None) -> dict[str, str]:
    """Send a progress notification to the system notification area.
    
    Args:
        stage: Current compilation stage (detection, warmup, compilation, etc.)
        progress: Progress percentage (0-100)
        message: Progress message to display
        eta_seconds: Estimated time remaining in seconds
    
    Returns:
        Dict with status and details about the notification
    """
    eta_msg = f" (ETA: {eta_seconds:.0f}s)" if eta_seconds else ""
    title = f"LaTeX Compilation - {stage.title()}"
    notification_text = f"{message}\nProgress: {progress:.0f}%{eta_msg}"
    
    success = send_system_notification(title, notification_text)
    
    return {
        "status": "sent" if success else "failed",
        "message": f"Progress notification: {stage} - {progress:.0f}%",
        "details": notification_text if success else "System notification unavailable"
    }

@mcp.tool() 
def send_task_complete_notification(task: str, details: str = "", success: bool = True) -> dict[str, str]:
    """Send a task completion notification.
    
    Args:
        task: Description of completed task
        details: Additional details about the task result
        success: Whether the task completed successfully
    
    Returns:
        Dict with notification status
    """
    title = "✓ Task Complete" if success else "✗ Task Failed"
    message = f"{task}\n{details}" if details else task
    
    notification_success = send_system_notification(title, message)
    
    return {
        "status": "sent" if notification_success else "failed", 
        "message": f"Task notification: {task}",
        "success": success
    }

@mcp.tool()
def send_error_notification(error: str, details: str = "") -> dict[str, str]:
    """Send an error notification.
    
    Args:
        error: Error description
        details: Additional error details or diagnostic information
    
    Returns:
        Dict with notification status
    """
    title = "⚠ Error Occurred"
    message = f"{error}\n{details}" if details else error
    
    success = send_system_notification(title, message)
    
    return {
        "status": "sent" if success else "failed",
        "message": f"Error notification: {error}"
    }

@mcp.tool()
def clear_data_files(keep_latest_pdf: bool = True, keep_latest_docx: bool = True) -> dict[str, str]:
    """Clear old files from data directory, optionally keeping latest PDF and DOCX files.
    
    Args:
        keep_latest_pdf: If True, keeps the most recently modified PDF file
        keep_latest_docx: If True, keeps the most recently modified DOCX file
    
    Returns:
        Dict with status and message about the cleanup operation
    """
    success, message = clear_data_directory(keep_latest_pdf, keep_latest_docx)
    return {
        "status": "success" if success else "error",
        "message": message
    }

@mcp.tool()
def reset_workflow() -> dict[str, str]:
    """Clear all loaded data and start fresh."""
    for key in ["resume_latex", "job_description", "company", "company_brief", "cover_letter_requested", "cover_letter_markdown", "cover_letter_request"]:
        STATE[key] = None
    # Keep user_info as it's personal and reusable across jobs
    return {"status": "reset", "message": "All job-specific data cleared (user info preserved)"}

if __name__ == "__main__":
    # Start LaTeX warmup automatically when server starts
    log.info("Starting MCP server and initializing LaTeX warmup...")
    _ensure_latex_warmed_up()
    mcp.run(transport="stdio")