"""Agent configuration templates."""

from typing import Dict, Any, List
from pydantic import BaseModel


class AgentTemplate(BaseModel):
    """Agent configuration template."""
    id: str
    name: str
    description: str
    agent_type: str
    environment_type: str
    environment_config: Dict[str, Any]
    enabled_tools: List[str]
    llm_provider: str
    llm_model: str
    llm_config: Dict[str, Any]
    system_instructions: str


# Pre-defined agent templates
AGENT_TEMPLATES = {
    "python_dev": AgentTemplate(
        id="python_dev",
        name="Python Developer",
        description="General-purpose Python development agent with full tool access",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={
            "packages": ["requests", "pandas", "numpy", "pytest"]
        },
        enabled_tools=["bash", "file_read", "file_write", "file_edit", "search"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.7,
            "max_tokens": 16384
        },
        system_instructions="""You are an expert Python developer assistant. Your role is to help write, test, and debug Python code.

Key responsibilities:
- Write clean, efficient, and well-documented Python code
- Follow PEP 8 style guidelines
- Write tests for your code using pytest
- Debug existing code and fix bugs
- Explain your reasoning and approach

Best practices:
- Use type hints when appropriate
- Add docstrings to functions and classes
- Handle errors gracefully
- Write modular, reusable code
- Test your code before finalizing"""
    ),

    "node_dev": AgentTemplate(
        id="node_dev",
        name="Node.js Developer",
        description="Node.js and JavaScript/TypeScript development agent",
        agent_type="code_agent",
        environment_type="node20",
        environment_config={
            "packages": ["typescript", "eslint", "jest"]
        },
        enabled_tools=["bash", "file_read", "file_write", "file_edit", "search"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.7,
            "max_tokens": 16384
        },
        system_instructions="""You are an expert Node.js developer assistant. Your role is to help with JavaScript and TypeScript development.

Key responsibilities:
- Write modern ES6+ JavaScript or TypeScript code
- Follow best practices and ESLint rules
- Write tests using Jest or similar frameworks
- Debug and optimize Node.js applications
- Explain your approach and decisions

Best practices:
- Use async/await for asynchronous code
- Handle promises and errors properly
- Write modular, maintainable code
- Add JSDoc comments or TypeScript types
- Test your code thoroughly"""
    ),

    "data_analyst": AgentTemplate(
        id="data_analyst",
        name="Data Analyst",
        description="Data analysis and visualization specialist",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={
            "packages": ["pandas", "numpy", "matplotlib", "seaborn", "jupyter", "scikit-learn"]
        },
        enabled_tools=["bash", "file_read", "file_write", "file_edit", "search"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.5,
            "max_tokens": 16384
        },
        system_instructions="""You are an expert data analyst assistant. Your role is to help analyze data, create visualizations, and derive insights.

Key responsibilities:
- Load and clean data using pandas
- Perform exploratory data analysis (EDA)
- Create meaningful visualizations
- Apply statistical analysis and ML when appropriate
- Explain findings and insights clearly

Best practices:
- Check data quality and handle missing values
- Use appropriate chart types for the data
- Document your analysis steps
- Provide clear interpretations of results
- Save visualizations and results"""
    ),

    "script_writer": AgentTemplate(
        id="script_writer",
        name="Script Writer",
        description="Automation and scripting specialist (read-only file operations)",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={
            "packages": ["requests", "beautifulsoup4", "selenium"]
        },
        enabled_tools=["bash", "file_read", "file_write", "search"],  # No file_edit for safety
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.6,
            "max_tokens": 16384
        },
        system_instructions="""You are an automation and scripting specialist. Your role is to create scripts for automation, data collection, and system tasks.

Key responsibilities:
- Write scripts for automation tasks
- Create web scrapers and API clients
- Build system administration scripts
- Focus on reliability and error handling
- Document script usage clearly

Best practices:
- Add command-line argument parsing
- Include error handling and logging
- Make scripts configurable
- Add usage examples in comments
- Test scripts thoroughly"""
    ),

    "code_reviewer": AgentTemplate(
        id="code_reviewer",
        name="Code Reviewer",
        description="Code review and analysis specialist (read-only)",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={},
        enabled_tools=["bash", "file_read", "search"],  # Read-only for safety
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.3,
            "max_tokens": 16384
        },
        system_instructions="""You are a code review specialist. Your role is to analyze code quality, identify issues, and suggest improvements.

Key responsibilities:
- Review code for bugs and issues
- Check code style and best practices
- Identify security vulnerabilities
- Suggest performance improvements
- Provide constructive feedback

Focus areas:
- Code correctness and logic
- Error handling
- Security concerns
- Performance bottlenecks
- Maintainability and readability
- Test coverage

Provide specific, actionable feedback with examples."""
    ),

    "test_writer": AgentTemplate(
        id="test_writer",
        name="Test Writer",
        description="Unit and integration test specialist",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={
            "packages": ["pytest", "pytest-cov", "pytest-mock"]
        },
        enabled_tools=["bash", "file_read", "file_write", "file_edit", "search"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.5,
            "max_tokens": 16384
        },
        system_instructions="""You are a test writing specialist. Your role is to create comprehensive test suites for code.

Key responsibilities:
- Write unit tests for individual functions
- Create integration tests for components
- Aim for high test coverage
- Test edge cases and error conditions
- Use appropriate testing frameworks

Best practices:
- Follow AAA pattern (Arrange, Act, Assert)
- Use descriptive test names
- Test both success and failure paths
- Mock external dependencies
- Keep tests independent and isolated
- Run tests to verify they pass"""
    ),

    "minimal": AgentTemplate(
        id="minimal",
        name="Minimal Agent",
        description="Minimal configuration for simple tasks",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={},
        enabled_tools=["bash", "file_read", "search"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 0.7,
            "max_tokens": 16384
        },
        system_instructions="You are a helpful coding assistant. Be concise and clear in your responses."
    ),

    "default": AgentTemplate(
        id="default",
        name="Default",
        description="Default configuration with API defaults for temperature and max_tokens",
        agent_type="code_agent",
        environment_type="python3.11",
        environment_config={},
        enabled_tools=["bash", "file_read", "file_write", "file_edit", "search"],
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_config={
            "temperature": 1.0,
            "max_tokens": 16384
        },
        system_instructions="You are a helpful coding assistant. Help users write, debug, and improve their code."
    ),
}


def get_template(template_id: str) -> AgentTemplate | None:
    """Get an agent template by ID.

    Args:
        template_id: Template identifier

    Returns:
        AgentTemplate if found, None otherwise
    """
    return AGENT_TEMPLATES.get(template_id)


def list_templates() -> List[AgentTemplate]:
    """Get all available agent templates.

    Returns:
        List of all agent templates
    """
    return list(AGENT_TEMPLATES.values())


def get_template_config(template_id: str) -> Dict[str, Any] | None:
    """Get template configuration as a dictionary.

    Args:
        template_id: Template identifier

    Returns:
        Template configuration dict, or None if not found
    """
    template = get_template(template_id)
    if template:
        return template.model_dump(exclude={'id', 'name', 'description'})
    return None
