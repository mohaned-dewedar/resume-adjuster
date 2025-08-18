#!/usr/bin/env python3
"""
Command-line tool runner for MCP tools.
Run any MCP tool directly from the terminal with arguments.
"""

import sys
import os
import json
import argparse
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Import all MCP tools
from resume_mcp.server import (
    load_resume, load_job_posting, load_job_posting_with_research,
    add_company_research, search_company_info_tool, load_user_info,
    get_workflow_status, submit_tailored_resume, submit_cover_letter,
    clear_data_files, reset_workflow, warmup_latex, get_compilation_status,
    export_document, get_conversion_status
)

# Map of tool names to functions
TOOLS = {
    'load_resume': load_resume,
    'load_job_posting': load_job_posting, 
    'load_job_posting_with_research': load_job_posting_with_research,
    'add_company_research': add_company_research,
    'search_company_info': search_company_info_tool,
    'load_user_info': load_user_info,
    'get_workflow_status': get_workflow_status,
    'submit_tailored_resume': submit_tailored_resume,
    'submit_cover_letter': submit_cover_letter,
    'clear_data_files': clear_data_files,
    'reset_workflow': reset_workflow,
    'warmup_latex': warmup_latex,
    'get_compilation_status': get_compilation_status,
    'export_document': export_document,
    'get_conversion_status': get_conversion_status,
}

def run_tool(tool_name, args):
    """Run a specific tool with provided arguments."""
    if tool_name not in TOOLS:
        print(f"❌ Tool '{tool_name}' not found!")
        print(f"Available tools: {', '.join(TOOLS.keys())}")
        return
    
    tool_func = TOOLS[tool_name]
    
    try:
        # Parse arguments and call the function
        if args:
            # Try to parse as JSON for complex arguments
            try:
                parsed_args = json.loads(' '.join(args))
                if isinstance(parsed_args, dict):
                    result = tool_func(**parsed_args)
                else:
                    result = tool_func(parsed_args)
            except json.JSONDecodeError:
                # Fallback: treat as positional arguments
                result = tool_func(*args)
        else:
            # No arguments
            result = tool_func()
        
        print("✅ Tool executed successfully!")
        print(f"Result: {json.dumps(result, indent=2)}")
        
    except Exception as e:
        print(f"❌ Error running tool: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(
        description="Run MCP tools directly from command line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Clear data directory
  python run_tool.py clear_data_files

  # Clear but don't keep any files
  python run_tool.py clear_data_files '{"keep_latest_pdf": false, "keep_latest_docx": false}'
  
  # Get workflow status
  python run_tool.py get_workflow_status
  
  # Reset workflow
  python run_tool.py reset_workflow
  
  # Load user info
  python run_tool.py load_user_info '{"full_name": "John Doe", "email": "john@example.com"}'
  
  # Search company info
  python run_tool.py search_company_info "Google"
  
  # Export document to Word
  python run_tool.py export_document "path/to/file.tex" "docx"
  
  # Get LaTeX status
  python run_tool.py get_compilation_status
"""
    )
    
    parser.add_argument('tool', help='Name of the MCP tool to run')
    parser.add_argument('args', nargs='*', help='Arguments for the tool (JSON or positional)')
    
    if len(sys.argv) == 1:
        parser.print_help()
        print(f"\nAvailable tools: {', '.join(TOOLS.keys())}")
        return
    
    args = parser.parse_args()
    run_tool(args.tool, args.args)

if __name__ == "__main__":
    main()