"""
Pydantic models for Resume MCP Server.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class CompilationResult(BaseModel):
    """Result of LaTeX compilation with detailed information."""
    success: bool = Field(description="Whether compilation succeeded")
    pdf_path: Optional[str] = Field(description="Path to generated PDF file if successful")
    tex_path: str = Field(description="Path to LaTeX source file")
    error_message: Optional[str] = Field(description="Error details if compilation failed")
    download_prompt: Optional[str] = Field(description="User-friendly download information")


class ConversionResult(BaseModel):
    """Result of document format conversion."""
    success: bool = Field(description="Whether conversion succeeded")
    output_path: Optional[str] = Field(description="Path to converted file if successful")
    format: str = Field(description="Target format (docx, pdf, html, txt)")
    error_message: Optional[str] = Field(description="Error details if conversion failed")


class CompilationProgress(BaseModel):
    """Progress tracking for LaTeX compilation."""
    stage: str = Field(description="Current compilation stage")
    progress: float = Field(description="Progress percentage (0-100)")
    message: str = Field(description="Progress message")
    eta_seconds: Optional[float] = Field(description="Estimated time remaining in seconds")


class UserInfo(BaseModel):
    """User information for cover letters and personalization."""
    full_name: str = Field(description="User's full name")
    email: str = Field(description="Contact email address")
    phone: Optional[str] = Field(description="Phone number")
    address: Optional[str] = Field(description="Mailing address")
    linkedin: Optional[str] = Field(description="LinkedIn profile URL")
    website: Optional[str] = Field(description="Personal website URL")


class SearchResult(BaseModel):
    """Result of company information search."""
    success: bool = Field(description="Whether search succeeded")
    company_info: Optional[str] = Field(description="Extracted company information")
    sources: List[str] = Field(description="URLs of information sources")
    error_message: Optional[str] = Field(description="Error details if search failed")