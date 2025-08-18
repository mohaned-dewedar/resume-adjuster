"""
Simplified LaTeX compilation using latexmk.
"""
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from .notifications import send_system_notification

log = logging.getLogger("resume-mcp")


def compile_pdf(tex_path: str) -> Tuple[bool, str, str]:
    """Compile TEX -> PDF using latexmk."""
    tex_file = Path(tex_path)
    workdir = tex_file.parent
    pdf_path = workdir / (tex_file.stem + ".pdf")
    
    # Check for latexmk
    latexmk_path = shutil.which("latexmk")
    if not latexmk_path:
        error_msg = "latexmk not found. Please install MiKTeX or TeX Live."
        log.error(error_msg)
        return (False, str(pdf_path), error_msg)
    
    # Verify input file exists
    if not tex_file.exists():
        error_msg = f"LaTeX file does not exist: {tex_file}"
        log.error(error_msg)
        return (False, str(pdf_path), error_msg)
    
    log.info(f"Compiling {tex_file.name} with latexmk")
    send_system_notification("LaTeX Compilation", f"Compiling {tex_file.name}...")
    
    try:
        # Run latexmk with optimized settings
        cmd = [
            "latexmk", 
            "-pdf",                    # Generate PDF
            "-interaction=nonstopmode", # Don't stop on errors
            "-halt-on-error",          # Exit on first error
            "-file-line-error",        # Better error reporting
            "-synctex=1",              # Enable SyncTeX for editors
            tex_file.name
        ]
        
        result = subprocess.run(
            cmd, 
            cwd=workdir, 
            capture_output=True, 
            text=True, 
            timeout=60  # Reduced timeout
        )
        
        if result.returncode == 0 and pdf_path.exists():
            log.info(f"Successfully compiled {tex_file.name}")
            send_system_notification("LaTeX Compilation", "PDF generated successfully")
            return (True, str(pdf_path), result.stdout)
        else:
            log.error(f"LaTeX compilation failed with return code {result.returncode}")
            send_system_notification("LaTeX Compilation", "Compilation failed", error=True)
            return (False, str(pdf_path), result.stderr or result.stdout)
            
    except subprocess.TimeoutExpired:
        error_msg = "LaTeX compilation timed out after 60 seconds"
        log.error(error_msg)
        send_system_notification("LaTeX Compilation", "Compilation timed out", error=True)
        return (False, str(pdf_path), error_msg)
    except Exception as e:
        error_msg = f"Exception during compilation: {e}"
        log.error(error_msg)
        send_system_notification("LaTeX Compilation", f"Error: {e}", error=True)
        return (False, str(pdf_path), error_msg)


def get_latex_status() -> dict:
    """Get status of LaTeX compilation system."""
    latexmk_path = shutil.which("latexmk")
    return {
        "latex_tool": "latexmk" if latexmk_path else "none",
        "latex_path": latexmk_path,
        "ready": bool(latexmk_path)
    }