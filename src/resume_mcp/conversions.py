"""
Document format conversion functionality.
"""
import logging
from pathlib import Path
from typing import Tuple, Optional

from .models import ConversionResult

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


def convert_markdown_to_word(markdown_path: str, output_format: str = "docx") -> Tuple[bool, str, str]:
    """Convert Markdown document to Word format using pandoc."""
    if not CONVERSION_AVAILABLE:
        return False, "", "Conversion libraries not available. Install pypandoc and python-docx."
    
    try:
        markdown_file = Path(markdown_path)
        if not markdown_file.exists():
            return False, "", f"Markdown file not found: {markdown_path}"
        
        # Generate output path
        output_path = markdown_file.with_suffix(f'.{output_format}')
        
        # Convert using pypandoc
        pypandoc.convert_file(
            str(markdown_file),
            output_format,
            outputfile=str(output_path),
            extra_args=['--reference-doc='] if output_format == 'docx' else []
        )
        
        if output_path.exists():
            return True, str(output_path), f"Successfully converted to {output_format.upper()}"
        else:
            return False, str(output_path), "Conversion completed but output file not found"
            
    except Exception as e:
        return False, str(markdown_file.with_suffix(f'.{output_format}')), f"Conversion failed: {str(e)}"




def get_conversion_capabilities() -> dict:
    """Check what document conversion tools are available."""
    tools = {
        "pypandoc": False,
        "pandoc": False,
        "python_docx": False
    }
    
    try:
        import pypandoc
        tools["pypandoc"] = True
        
        # Check if pandoc binary is available
        pandoc_version = pypandoc.get_pandoc_version()
        tools["pandoc"] = pandoc_version is not None
        
    except ImportError:
        pass
    except Exception:
        # pypandoc installed but pandoc binary missing
        tools["pypandoc"] = True
        tools["pandoc"] = False
    
    try:
        import docx
        tools["python_docx"] = True
    except ImportError:
        pass
    
    return {
        "conversion_available": CONVERSION_AVAILABLE,
        "pypandoc_installed": tools["pypandoc"],
        "pandoc_installed": tools["pandoc"],
        "python_docx_available": tools["python_docx"],
        "supported_formats": ["docx", "pdf", "html", "txt"] if CONVERSION_AVAILABLE else [],
        "recommended_format": "docx" if tools["pandoc"] else "pdf",
        "recommendation": "Use docx format for easy uploading to job portals" if tools["pandoc"] else "Install pandoc for Word conversion"
    }