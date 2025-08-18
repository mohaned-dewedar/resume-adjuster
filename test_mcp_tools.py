#!/usr/bin/env python3
"""
Manual testing examples for MCP tools.
Run these to test individual tools with arguments.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Import the server functions directly
from resume_mcp.server import (
    load_resume, load_job_posting, load_job_posting_with_research,
    add_company_research, search_company_info_tool, load_user_info,
    get_workflow_status, submit_tailored_resume, submit_cover_letter,
    clear_data_files, reset_workflow, warmup_latex, get_compilation_status,
    export_document, get_conversion_status, STATE
)

def test_basic_workflow():
    """Test the basic resume generation workflow."""
    print("=== Testing Basic Workflow ===\n")
    
    # 1. Reset workflow
    print("1. Resetting workflow...")
    result = reset_workflow()
    print(f"   {result}\n")
    
    # 2. Load base resume
    print("2. Loading base resume...")
    sample_resume = r"""
\documentclass[letterpaper,11pt]{article}
\usepackage[left=0.75in,top=0.6in,right=0.75in,bottom=0.6in]{geometry}
\begin{document}
\textbf{\Large JOHN DOE}\\
Email: john@example.com | Phone: (555) 123-4567

\section{Experience}
\textbf{Software Engineer | Tech Company} \hfill Jan 2024 -- Present
\begin{itemize}
\item Developed applications using Python and JavaScript
\item Collaborated with teams to deliver features
\end{itemize}

\section{Skills}
\textbf{Technical:} Python, JavaScript, React, SQL
\end{document}
"""
    result = load_resume(sample_resume)
    print(f"   {result}\n")
    
    # 3. Load job posting with research
    print("3. Loading job posting with company research...")
    job_desc = """
Senior Software Engineer
We're looking for a senior software engineer to join our team.
Requirements:
- 5+ years Python experience
- React/JavaScript expertise
- SQL database experience
- Team leadership skills
"""
    result = load_job_posting_with_research(job_desc, "Google", auto_research=True)
    print(f"   {result}\n")
    
    # 4. Check workflow status
    print("4. Checking workflow status...")
    result = get_workflow_status()
    print(f"   Ready for generation: {result['status']['ready_for_generation']}")
    print(f"   Next steps: {result['next_steps']}\n")

def test_user_info_and_cover_letter():
    """Test user info loading and cover letter generation."""
    print("=== Testing User Info & Cover Letter ===\n")
    
    # 1. Load user info
    print("1. Loading user information...")
    result = load_user_info(
        full_name="John Doe",
        email="john@example.com", 
        phone="(555) 123-4567",
        address="123 Main St, City, ST 12345",
        linkedin="linkedin.com/in/johndoe"
    )
    print(f"   {result}\n")
    
    # 2. Test cover letter generation  
    print("2. Generating cover letter...")
    cover_letter_body = """
I am excited to apply for the Senior Software Engineer position at Google. With over 5 years of Python experience and extensive React/JavaScript expertise, I am confident I would be a valuable addition to your team.

In my current role, I have led development teams and delivered critical features using the exact technology stack mentioned in your job posting. My experience with SQL databases and collaborative development makes me well-suited for this position.

I am particularly drawn to Google's innovative culture and would love to contribute to your mission of organizing the world's information.
"""
    
    result = submit_cover_letter("john_doe_google_cover_letter", cover_letter_body, auto_convert_to_word=True)
    print(f"   Success: {result['success']}")
    print(f"   Files: {result.get('files', {})}\n")

def test_compilation_and_status():
    """Test LaTeX compilation and status functions."""
    print("=== Testing Compilation & Status ===\n")
    
    # 1. Check compilation status
    print("1. Checking LaTeX compilation status...")
    result = get_compilation_status()
    print(f"   LaTeX tool: {result['latex_tool']}")
    print(f"   Warmed up: {result['latex_warmed_up']}")
    print(f"   Recommendation: {result['recommendation']}\n")
    
    # 2. Warmup LaTeX
    print("2. Starting LaTeX warmup...")
    result = warmup_latex()
    print(f"   {result}\n")
    
    # 3. Check conversion capabilities
    print("3. Checking conversion capabilities...")
    result = get_conversion_status()
    print(f"   Conversion available: {result['conversion_available']}")
    print(f"   Pandoc installed: {result['pandoc_installed']}")
    print(f"   Supported formats: {result['supported_formats']}\n")

def test_file_management():
    """Test file management functions."""
    print("=== Testing File Management ===\n")
    
    # 1. Check current state
    print("1. Current workflow status...")
    result = get_workflow_status()
    print(f"   Data location: {result['data_location']}")
    print(f"   Current company: {result.get('current_company', 'None')}\n")
    
    # 2. Clear data files (but keep latest)
    print("2. Clearing old data files...")
    result = clear_data_files(keep_latest_pdf=True, keep_latest_docx=True)
    print(f"   {result}\n")

def test_company_research():
    """Test company research functionality."""
    print("=== Testing Company Research ===\n")
    
    # 1. Manual company research
    print("1. Adding manual company research...")
    company_brief = """
Microsoft Corporation is a multinational technology company headquartered in Redmond, Washington. 
Founded in 1975, Microsoft develops, manufactures, licenses, supports, and sells computer software, 
consumer electronics, personal computers, and related services. Key products include Windows OS, 
Microsoft Office suite, Azure cloud platform, and Xbox gaming console.

Company Culture: Innovation-focused, collaborative environment with emphasis on diversity and inclusion.
Recent Focus: Cloud computing (Azure), AI integration, sustainable technology solutions.
"""
    result = add_company_research(company_brief)
    print(f"   {result}\n")
    
    # 2. Web-based company search
    print("2. Searching for company information online...")
    result = search_company_info_tool("Apple")
    print(f"   Success: {result['success']}")
    print(f"   Info preview: {result.get('company_info', 'None')[:100]}...")
    print(f"   Sources: {result.get('sources', [])}\n")

def run_all_tests():
    """Run all test functions."""
    print("🧪 MCP Tools Manual Testing\n")
    
    try:
        test_basic_workflow()
        test_user_info_and_cover_letter() 
        test_compilation_and_status()
        test_file_management()
        test_company_research()
        
        print("✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Available test functions:")
    print("- test_basic_workflow()")
    print("- test_user_info_and_cover_letter()")  
    print("- test_compilation_and_status()")
    print("- test_file_management()")
    print("- test_company_research()")
    print("- run_all_tests()\n")
    
    # Run all tests by default
    run_all_tests()