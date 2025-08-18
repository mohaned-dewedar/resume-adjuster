"""
File storage and data directory management.
"""
import logging
import re
from pathlib import Path
from typing import Tuple

log = logging.getLogger("resume-mcp")

# Storage paths
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
PROMPTS_DIR = DATA_DIR / "prompts"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)


def save_text(filename: str, content: str) -> str:
    """Save text content to a file in the data directory with collision avoidance."""
    base_name = filename
    if not base_name.endswith(('.tex', '.txt', '.md')):
        base_name += '.tex'  # Default extension
    
    file_path = DATA_DIR / base_name
    counter = 1
    
    # Handle filename collisions
    while file_path.exists():
        name_part = Path(base_name).stem
        ext_part = Path(base_name).suffix
        file_path = DATA_DIR / f"{name_part}_v{counter}{ext_part}"
        counter += 1
    
    # Write the file
    file_path.write_text(content, encoding='utf-8')
    log.info(f"Saved file: {file_path}")
    return str(file_path)


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use as a filename."""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


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


def get_data_dir() -> Path:
    """Get the data directory path."""
    return DATA_DIR


def get_prompts_dir() -> Path:
    """Get the prompts directory path."""
    return PROMPTS_DIR