# Resume MCP Server Setup with UV

## Installation Steps

### 1. Install UV (if not already installed)
```powershell
# Run in PowerShell
irm https://astral.sh/uv/install.ps1 | iex
```

### 2. Setup Project
```bash
# Navigate to project directory
cd C:\Users\mdewe\OneDrive\Desktop\github\resume-mcp

# Install dependencies with uv
uv sync
```

### 3. Test Server
```bash
# Test the server works
uv run python -m resume_mcp.server
```

## Claude Desktop Configuration

Copy this configuration to your Claude Desktop MCP settings:

```json
{
  "mcpServers": {
    "resume-mcp": {
      "command": "C:\\Users\\mdewe\\.local\\bin\\uv.exe",
      "args": [
        "--directory",
        "C:\\Users\\mdewe\\OneDrive\\Desktop\\github\\resume-mcp",
        "run",
        "python",
        "-m",
        "resume_mcp.server"
      ],
      "env": {}
    }
  }
}
```

## Features Available

✅ **Fixed Issues:**
- Pydantic schema error resolved
- UV properly installed and configured
- Server runs successfully with LaTeX warmup
- All cover letter functionality working

✅ **Available Features:**
- Resume tailoring with LaTeX compilation
- Company research with web search
- Cover letter generation with interactive elicitation
- PDF compilation with multiple LaTeX tools
- MCP integration with structured outputs

## Usage

The server provides:
- **Resources**: Access to resume, job description, company data, prompts
- **Tools**: Load data, search companies, generate resumes/cover letters
- **Web Search**: Automatic company research via DuckDuckGo API
- **Cover Letters**: Interactive preference setting and generation
- **LaTeX**: Automatic warmup and PDF compilation

Ready to use with Claude Desktop!