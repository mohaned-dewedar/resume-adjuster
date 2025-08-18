# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python MCP (Model Context Protocol) server that provides AI-powered resume tailoring functionality. The server helps users automatically customize LaTeX resumes for specific job postings, with support for company research integration and PDF compilation.

## Development Commands

### Environment Setup
```bash
# Install uv if not already installed (Windows)
powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"

# Add uv to PATH for current session (Windows)
set Path=C:\Users\%USERNAME%\.local\bin;%Path%

# Install dependencies using uv (modern Python package manager)
uv sync

# Install in development mode
uv pip install -e .
```

### Running the Server
```bash
# Run the MCP server with stdio transport
uv run python -m resume_mcp.server

# Alternative: Run from the package (after installation)
uv run resume-mcp

# For Windows PowerShell (if uv not in PATH):
C:\Users\mdewe\.local\bin\uv.exe run python -m resume_mcp.server
```

### Testing LaTeX Compilation
The server automatically detects available LaTeX tools in this order:
1. `latexmk` (preferred) - requires MiKTeX or TeX Live
2. `pdflatex` (fallback) - runs twice for proper references
3. `pandoc` (basic fallback)

### Building Package
```bash
# Build wheel and source distribution
uv build

# Install locally
uv pip install dist/resume_mcp-*.whl
```

## Architecture

### Core Components

**MCP Server (`server.py`)**
- Built using FastMCP framework
- Provides both resources (read-only data) and tools (actions)
- Manages state for resume, job description, and company research
- Handles LaTeX compilation and PDF generation

**State Management**
- Global `STATE` dict stores: `resume_latex`, `job_description`, `company`, `company_brief`
- Persistent storage in `data/` directory for all inputs and outputs
- Automatic filename generation with collision avoidance

**Data Flow**
1. Load base resume (LaTeX) via `load_resume()` tool
2. Load job posting via `load_job_posting()` tool OR `load_job_posting_with_research()` for automatic company research
3. Optionally add/search company research via `add_company_research()` or `search_company_info()` tools
4. AI agent reads data via resources and generates tailored resume
5. AI calls `submit_tailored_resume()` tool with final LaTeX
6. Server compiles LaTeX to PDF and returns compilation result

### MCP Resources (Read-only)
- `resume://base` - Current base resume LaTeX
- `job://description` - Current job description
- `company://brief` - Company research brief
- `prompts://system` - System prompt template
- `prompts://user-template` - User prompt template  
- `prompts://complete` - Complete formatted prompt
- `search://capabilities` - Available web search functionality

### MCP Tools (Actions)
- `load_resume(latex)` - Load base resume
- `load_job_posting(description, company_name?)` - Load job posting
- `load_job_posting_with_research(description, company_name, auto_research=True)` - Load job posting with automatic company research
- `add_company_research(brief)` - Add company research manually
- `search_company_info(company_name)` - Search web for company information and auto-add to brief
- `load_user_info(full_name, email, ...)` - Load personal info for cover letters
- `elicit_cover_letter_preference()` - Ask user if they want cover letter
- `set_cover_letter_preference(wants_cover_letter, ...)` - Set cover letter preferences
- `get_workflow_status()` - Get current workflow state
- `submit_tailored_resume(filename_stem, latex_body)` - Generate final resume
- `submit_cover_letter(filename_stem, cover_letter_body, auto_convert_to_word=True)` - Generate cover letter (auto-converts to Word)
- `export_document(tex_file_path, output_format="docx")` - Convert LaTeX to Word/PDF/HTML/TXT formats
- `get_conversion_status()` - Check document conversion capabilities
- `reset_workflow()` - Clear all data

### File Structure
```
src/resume_mcp/
├── server.py          # Main MCP server
├── __init__.py         # Empty package marker
└── data/               # Runtime data storage
    ├── prompts/        # Custom prompt templates (optional)
    ├── *.tex           # Generated resume files
    ├── *.pdf           # Compiled PDF outputs
    ├── *.docx          # Word format outputs (for job portals)
    └── *.txt           # Job descriptions, company briefs
```

## Document Conversion Features

The server includes automatic document conversion capabilities to generate job-portal-ready formats:

### Supported Output Formats
- **Word (.docx)** - Recommended for job portal uploads and ATS systems
- **PDF** - Standard format for viewing and email attachments
- **HTML** - Web-friendly format
- **TXT** - Plain text format

### Automatic Conversion
- Cover letters are automatically generated in both PDF and Word formats
- Use `export_document()` tool to convert any LaTeX file to desired format
- Word format is specifically optimized for ATS compatibility

### Requirements for Word Conversion
```bash
# Install pandoc for document conversion (Windows)
winget install --id JohnMacFarlane.Pandoc

# Or download from: https://pandoc.org/installing.html
```

## Customization

### Custom Prompts
Create files in `data/prompts/` to override defaults:
- `system.txt` - Override system prompt
- `user.txt` - Override user prompt template (must include `{resume}`, `{jd}`, `{brief}` placeholders)

### LaTeX Templates
The base resume template uses standard LaTeX packages for ATS compatibility. Generated resumes follow these constraints:
- Minimal custom packages/macros
- One page target length
- ATS-friendly formatting
- Bold keywords matching job requirements

## Web Search Features

The server includes automated company research capabilities to enhance resume tailoring:

### Search Sources
- **DuckDuckGo Instant Answers API** - Primary source for company information
- **Fallback Guidance** - Structured research prompts when APIs are unavailable

### Automatic Research Workflow
1. Use `load_job_posting_with_research()` instead of `load_job_posting()`
2. Server automatically searches for company information
3. Results are parsed and added to `company_brief` in STATE
4. Search results are saved as `company_brief_<company>.txt` in data directory

### Manual Research
- Call `search_company_info(company_name)` at any time
- Results automatically update the company brief
- View search capabilities via `search://capabilities` resource

### Search Result Structure
```python
class SearchResult(BaseModel):
    success: bool                    # Whether search succeeded
    company_info: Optional[str]      # Extracted company information  
    sources: List[str]              # URLs of information sources
    error_message: Optional[str]     # Error details if failed
```

## Integration Notes

This MCP server is designed to integrate with Claude via the MCP protocol. The AI agent:
1. Reads available data through MCP resources
2. Uses the complete prompt resource to understand the full context
3. Optionally leverages web search for enhanced company research
4. Calls `submit_tailored_resume()` with structured output when ready
5. Receives compilation feedback through the `CompilationResult` model

The workflow is stateful - each tool call updates the global state, and resources reflect the current state for the AI agent to read.