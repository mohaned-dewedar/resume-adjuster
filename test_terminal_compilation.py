#!/usr/bin/env python3
"""Test progress terminal with actual LaTeX compilation."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from resume_mcp.server import _compile_pdf_with_progress, ProgressCallback, _save_text

def test_terminal_with_compilation():
    """Test progress terminal with real LaTeX compilation."""
    print("Testing progress terminal with LaTeX compilation...")
    
    # Create simple test document
    latex_content = r'''
\documentclass[letterpaper,11pt]{article}
\usepackage[left=0.75in,top=0.6in,right=0.75in,bottom=0.6in]{geometry}
\begin{document}
\textbf{Terminal Test Document}

This is a test LaTeX document to verify terminal progress display works.
\end{document}
'''
    
    # Save the test document
    tex_path = _save_text("terminal_test.tex", latex_content)
    print(f"Created test document: {tex_path}")
    
    # Create progress callback with terminal
    callback = ProgressCallback(terminal_title="LaTeX Test Compilation")
    
    try:
        # Run compilation with progress terminal
        success, pdf_path, build_log = _compile_pdf_with_progress(tex_path, callback)
        
        if success:
            print(f"SUCCESS: PDF created at {pdf_path}")
            print("Check if you saw a progress terminal window during compilation!")
        else:
            print(f"FAILED: {build_log}")
            
    finally:
        callback.close_terminal()

if __name__ == "__main__":
    test_terminal_with_compilation()