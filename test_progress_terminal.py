#!/usr/bin/env python3
"""Test script for progress terminal functionality."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from resume_mcp.server import ProgressCallback
import time

def test_progress_terminal():
    """Test the progress terminal display."""
    print("Testing progress terminal...")
    
    # Create progress callback with terminal
    callback = ProgressCallback(terminal_title="Test Progress Terminal")
    
    try:
        # Simulate compilation stages
        callback.log_stage("detection", "Detecting LaTeX tools")
        time.sleep(1)
        
        callback.update("detection", 100.0, "Found latexmk")
        time.sleep(1)
        
        callback.log_stage("compilation", "Running LaTeX compilation")
        time.sleep(1)
        
        callback.update("compilation", 25.0, "Processing document structure", 3.0)
        time.sleep(1)
        
        callback.update("compilation", 50.0, "Building references", 2.0)
        time.sleep(1)
        
        callback.update("compilation", 75.0, "Generating output", 1.0)
        time.sleep(1)
        
        callback.complete_stage("compilation", "PDF generated successfully")
        time.sleep(2)
        
        print("Test completed - check if terminal window appeared with progress updates")
        
    finally:
        callback.close_terminal()

if __name__ == "__main__":
    test_progress_terminal()