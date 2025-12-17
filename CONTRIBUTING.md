# Contributing to Open Claude UI

Thank you for your interest in contributing to Open Claude UI! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker 20.10+
- Poetry (for Python dependency management)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/zysoong/open-claude-ui.git
   cd open-claude-ui
   ```

2. **Backend setup**
   ```bash
   cd backend
   poetry install --with dev
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Frontend setup**
   ```bash
   cd frontend
   npm install
   ```

4. **Run the development servers**
   ```bash
   # Terminal 1 - Backend
   cd backend
   poetry run python -m app.main

   # Terminal 2 - Frontend
   cd frontend
   npm run dev
   ```

## Development Workflow

### Code Style

**Backend (Python)**
- We use [Black](https://black.readthedocs.io/) for code formatting
- We use [Ruff](https://docs.astral.sh/ruff/) for linting
- Run before committing:
  ```bash
  cd backend
  poetry run black .
  poetry run ruff check .
  ```

**Frontend (TypeScript)**
- We use TypeScript for type safety
- Run type checking:
  ```bash
  cd frontend
  npx tsc --noEmit
  ```

### Running Tests

**Backend**
```bash
cd backend
poetry run pytest                          # All tests
poetry run pytest tests/ --ignore=tests/integration  # Unit tests only
poetry run pytest tests/integration        # Integration tests only
```

**Frontend**
```bash
cd frontend
npm run test:unit      # Unit tests
npm run test:e2e       # E2E tests (requires backend running)
```

### Pull Request Process

1. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and ensure:
   - All tests pass
   - Code follows the style guidelines
   - New features include tests

3. **Commit your changes** with clear, descriptive messages

4. **Push and create a Pull Request** against the `main` branch

5. **Wait for review** - maintainers will review your PR and may request changes

## Areas for Contribution

### High Priority
- Bug fixes
- Documentation improvements
- Test coverage improvements

### Feature Ideas
- New agent tools
- Additional LLM provider integrations
- UI/UX improvements
- Performance optimizations
- New language environment support

## Reporting Issues

When reporting issues, please include:
- A clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, Node version, etc.)
- Relevant logs or error messages

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Focus on the code, not the person
- Help others learn and grow

## Questions?

If you have questions about contributing, feel free to open an issue for discussion.

Thank you for contributing to Open Claude UI!
