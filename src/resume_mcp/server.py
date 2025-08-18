"""
Refactored Resume MCP Server using modular components.
"""
import sys
import logging
import json
import requests
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

# Import our modules
from .models import CompilationResult, ConversionResult, UserInfo, SearchResult
from .notifications import send_system_notification
from .latex import compile_pdf, get_latex_status
from .conversions import convert_markdown_to_word, get_conversion_capabilities
from .storage import save_text, clear_data_directory, get_data_dir
from .prompts import (
    get_system_prompt, get_user_template, format_complete_prompt,
    create_cover_letter_template_markdown
)

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
log = logging.getLogger("resume-mcp")

# -----------------------------
# Global State
# -----------------------------
STATE: Dict[str, Any] = {
    "resume_latex": None,
    "job_description": None,
    "company": None,
    "company_brief": None,
    "user_info": None,
    "cover_letter_requested": None,
    "cover_letter_markdown": None,
    "cover_letter_request": None,
}

# -----------------------------
# Company Research
# -----------------------------
def search_company_info(company_name: str) -> SearchResult:
    """Search for company information using web APIs."""
    try:
        encoded_name = urllib.parse.quote(company_name)
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
def get_system_prompt_resource():
    """Get the system prompt template (customizable via data/prompts/system.txt)."""
    return get_system_prompt()

@mcp.resource("prompts://user-template")
def get_user_template_resource():
    """Get the user prompt template (customizable via data/prompts/user.txt)."""
    return get_user_template()

@mcp.resource("prompts://complete")
def get_complete_prompt():
    """Get the complete, ready-to-use prompt for Claude."""
    return format_complete_prompt(
        STATE.get("resume_latex", ""),
        STATE.get("job_description", ""),
        STATE.get("company_brief")
    )

@mcp.resource("search://capabilities")
def get_search_capabilities():
    """Get information about available search functionality."""
    return """Web Search Capabilities:

Available Sources:
- DuckDuckGo Instant Answers API for company overviews
- Structured fallback prompts when APIs are unavailable

Usage:
- Call search_company_info(company_name) to automatically research companies
- Results are cached in company_brief for resume tailoring
- Manual research prompts provided when automated search fails

The search functionality enhances resume tailoring by providing company context, 
business model information, and cultural insights for better job application customization."""

# -----------------------------
# MCP Tools (Actions)
# -----------------------------
@mcp.tool()
def load_resume(latex: str) -> dict[str, str]:
    """Load base resume LaTeX content."""
    STATE["resume_latex"] = latex.strip()
    # Save to file for backup
    save_text("resume_base.tex", latex.strip())
    return {"status": "loaded", "message": "Base resume loaded successfully"}

@mcp.tool()
def load_job_posting(description: str, company_name: str = "") -> dict[str, str]:
    """Load job posting description and optional company name."""
    STATE["job_description"] = description.strip()
    STATE["company"] = company_name.strip() if company_name else None
    
    # Save to files
    save_text("job_description.txt", description.strip())
    
    return {
        "status": "loaded",
        "message": f"Job description loaded{f' for {company_name}' if company_name else ''}"
    }

@mcp.tool()
def load_job_posting_with_research(description: str, company_name: str, auto_research: bool = True) -> dict[str, str]:
    """Load job posting and automatically research the company."""
    STATE["job_description"] = description.strip()
    STATE["company"] = company_name.strip()
    
    # Save job description
    save_text("job_description.txt", description.strip())
    
    if auto_research and company_name:
        result = search_company_info(company_name)
        if result.success and result.company_info:
            STATE["company_brief"] = result.company_info
            # Save company brief
            from .storage import sanitize_filename
            filename = f"company_brief_{sanitize_filename(company_name)}.txt"
            save_text(filename, result.company_info)
            
            return {
                "status": "loaded_with_research",
                "message": f"Job description and company research loaded for {company_name}",
                "company_info": result.company_info[:200] + "..." if len(result.company_info) > 200 else result.company_info,
                "sources": result.sources
            }
    
    return {
        "status": "loaded",
        "message": f"Job description loaded for {company_name}. Use search_company_info() for research."
    }

@mcp.tool()
def add_company_research(brief: str) -> dict[str, str]:
    """Manually add company research brief."""
    STATE["company_brief"] = brief.strip()
    
    # Save to file if we know the company name
    if STATE.get("company"):
        from .storage import sanitize_filename
        filename = f"company_brief_{sanitize_filename(STATE['company'])}.txt"
        save_text(filename, brief.strip())
    else:
        save_text("company_brief_.txt", brief.strip())
    
    return {"status": "added", "message": "Company research brief added"}

@mcp.tool()
def search_company_info_tool(company_name: str) -> dict[str, Any]:
    """Search web for company information and add to brief."""
    result = search_company_info(company_name)
    
    if result.success and result.company_info:
        STATE["company_brief"] = result.company_info
        STATE["company"] = company_name  # Update company name
        
        # Save company brief
        from .storage import sanitize_filename
        filename = f"company_brief_{sanitize_filename(company_name)}.txt"
        save_text(filename, result.company_info)
        
    return {
        "success": result.success,
        "company_info": result.company_info,
        "sources": result.sources,
        "error_message": result.error_message,
        "message": "Company information added to brief" if result.success else "Search failed"
    }

@mcp.tool()
def load_user_info(full_name: str, email: str, phone: str = "", address: str = "", 
                   linkedin: str = "", website: str = "") -> dict[str, str]:
    """Load user personal information for cover letters."""
    user_info = UserInfo(
        full_name=full_name.strip(),
        email=email.strip(),
        phone=phone.strip() if phone else None,
        address=address.strip() if address else None,
        linkedin=linkedin.strip() if linkedin else None,
        website=website.strip() if website else None
    )
    STATE["user_info"] = user_info
    
    # Save to JSON for persistence
    user_data = user_info.dict()
    save_text("user_info.json", json.dumps(user_data, indent=2))
    
    return {"status": "loaded", "message": f"User information loaded for {full_name}"}

@mcp.tool()
def get_workflow_status() -> dict[str, Any]:
    """Get current workflow state and what's needed next."""
    status = {
        "resume_loaded": bool(STATE.get("resume_latex")),
        "job_loaded": bool(STATE.get("job_description")),
        "company_identified": bool(STATE.get("company")),
        "company_researched": bool(STATE.get("company_brief")),
        "user_info_loaded": bool(STATE.get("user_info")),
        "cover_letter_preference_set": STATE.get("cover_letter_requested") is not None,
        "ready_for_generation": bool(STATE.get("resume_latex") and STATE.get("job_description"))
    }
    
    next_steps = []
    if not status["resume_loaded"]:
        next_steps.append("Load base resume with load_resume()")
    if not status["job_loaded"]:
        next_steps.append("Load job posting with load_job_posting()")
    if status["job_loaded"] and not status["company_researched"]:
        next_steps.append("Research company with search_company_info() or add_company_research()")
    if not status["user_info_loaded"]:
        next_steps.append("Load user info with load_user_info() for cover letters")
    if status["ready_for_generation"]:
        next_steps.append("Ready to generate resume with submit_tailored_resume()")
    
    return {
        "status": status,
        "next_steps": next_steps,
        "current_company": STATE.get("company"),
        "data_location": str(get_data_dir())
    }

@mcp.tool()
def submit_tailored_resume(filename_stem: str, latex_body: str) -> CompilationResult:
    """Generate the final tailored resume with LaTeX compilation and progress tracking."""
    try:
        import os
        from pathlib import Path
        
        # Sanitize filename
        from .storage import sanitize_filename
        stem = sanitize_filename(filename_stem) or "resume"
        log.info(f"Processing resume: {stem}")
        
        # Save LaTeX and compile with warmup support
        tex_path = save_text(f"{stem}.tex", latex_body.strip())
        
        # Verify file exists and is readable
        tex_file = Path(tex_path)
        if not tex_file.exists():
            error_msg = f"ERROR: LaTeX file was not created at {tex_path}"
            log.error(error_msg)
            return CompilationResult(
                success=False,
                pdf_path=None,
                tex_path=tex_path,
                error_message=error_msg,
                download_prompt=None
            )
        
        # Start compilation in background thread - LLM doesn't wait
        import threading
        
        def background_compile():
            log.info(f"Starting background compilation: {stem}")
            success, pdf_path, build_log = compile_pdf(tex_path)
            
            if success:
                log.info(f"Resume compilation successful: {os.path.basename(pdf_path)}")
                send_system_notification(
                    "✅ Resume Ready!", 
                    f"PDF generated: {os.path.basename(pdf_path)}"
                )
            else:
                log.error(f"Resume compilation failed for {stem}")
                if build_log:
                    log.error(f"Error details: {build_log[-500:]}")
                send_system_notification(
                    "❌ Compilation Failed", 
                    f"LaTeX compilation failed for {stem}"
                )
        
        # Start background thread
        compile_thread = threading.Thread(target=background_compile, daemon=True)
        compile_thread.start()
        
        # Return immediately to LLM with LaTeX saved
        tex_name = os.path.basename(tex_path)
        expected_pdf = os.path.basename(tex_path).replace('.tex', '.pdf')
        
        result = CompilationResult(
            success=True,  # LaTeX saved successfully
            pdf_path=None,  # Will be available soon via background compilation
            tex_path=tex_path,
            error_message=None,
            download_prompt=f"Resume submitted for compilation!\n\n• LaTeX saved: {tex_name}\n• PDF will be ready shortly: {expected_pdf}\n\nLocation: {get_data_dir()}\n\nYou'll receive a notification when the PDF is ready!"
        )
        
        return result
        
    except Exception as e:
        error_msg = f"Exception in submit_tailored_resume: {str(e)}"
        log.error(error_msg)
        log.error("Exception traceback:", exc_info=True)
        
        return CompilationResult(
            success=False,
            pdf_path=None,
            tex_path=tex_path if 'tex_path' in locals() else "unknown",
            error_message=error_msg,
            download_prompt=None
        )

@mcp.tool()
def submit_cover_letter(filename_stem: str, cover_letter_body: str, auto_convert_to_word: bool = True) -> dict:
    """Generate cover letter from body content using Markdown workflow."""
    if not STATE.get("user_info"):
        return {
            "success": False,
            "error": "User information required. Use load_user_info() first."
        }
    
    # Sanitize filename
    from .storage import sanitize_filename
    stem = sanitize_filename(filename_stem) or "cover_letter"
    company = STATE.get("company", "Company")
    position = "Position"  # Could be extracted from job description
    
    # Create markdown template and insert body
    template = create_cover_letter_template_markdown(STATE["user_info"], company, position)
    markdown_content = template.replace("{COVER_LETTER_BODY}", cover_letter_body.strip())
    
    # Save markdown
    markdown_path = save_text(f"{stem}.md", markdown_content)
    
    results = {"markdown_path": markdown_path}
    
    # Convert to Word if requested
    if auto_convert_to_word:
        success, word_path, message = convert_markdown_to_word(markdown_path, "docx")
        results["word_conversion"] = {
            "success": success,
            "path": word_path if success else None,
            "message": message
        }
        
        # Send notification
        if success:
            send_system_notification("✓ Cover Letter Ready!", f"Generated in Word format: {Path(word_path).name}")
        else:
            send_system_notification("⚠ Conversion Issue", f"Cover letter created but Word conversion failed: {message}")
    
    STATE["cover_letter_markdown"] = markdown_content
    
    return {
        "success": True,
        "message": "Cover letter generated successfully",
        "files": results,
        "location": str(get_data_dir())
    }

@mcp.tool()
def warmup_latex() -> dict[str, str]:
    """Check LaTeX availability (warmup no longer needed with simplified compilation)."""
    status = get_latex_status()
    return {"status": "ready" if status["ready"] else "unavailable", "message": f"LaTeX tool: {status['latex_tool']}"}

@mcp.tool()
def get_compilation_status() -> dict:
    """Get status of LaTeX compilation system."""
    return get_latex_status()


@mcp.tool()
def get_conversion_status() -> dict:
    """Check what document conversion capabilities are available."""
    return get_conversion_capabilities()

# Notification functions are now background-only, not MCP tools
# They're automatically called during operations like submit_tailored_resume

@mcp.tool()
def clear_data_files(keep_latest_pdf: bool = True, keep_latest_docx: bool = True) -> dict[str, str]:
    """Clear old files from data directory, optionally keeping latest PDF and DOCX files."""
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
    log.info("Starting MCP server...")
    mcp.run(transport="stdio")