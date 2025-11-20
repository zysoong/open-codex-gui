# Testing Quick Start Guide

Quick reference for running tests in the Open Codex GUI project.

---

## Backend Tests

### Setup
```bash
cd backend
poetry install
```

### Run All Tests
```bash
# Basic run
poetry run pytest

# With coverage
poetry run pytest --cov=app --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Run Specific Tests
```bash
# API tests only
poetry run pytest -m api

# Skip Docker tests
poetry run pytest -m "not container"

# One file
poetry run pytest tests/integration/test_api_projects.py

# One test
poetry run pytest tests/integration/test_api_projects.py::TestProjectAPI::test_create_project
```

### Parallel Execution (Faster)
```bash
poetry run pytest -n auto
```

**Total: 88 integration tests**

---

## Frontend E2E Tests

### Setup
```bash
cd frontend
npm install
```

### Run All E2E Tests
```bash
# With UI (recommended)
npm run test:e2e:ui

# Headless
npm run test:e2e

# See browser
npm run test:e2e:headed
```

### Run Specific Tests
```bash
# Project management
npx playwright test tests/e2e/project-management.spec.ts

# Chat session
npx playwright test tests/e2e/chat-session.spec.ts

# Agent config
npx playwright test tests/e2e/agent-config.spec.ts
```

### Debug Mode
```bash
npm run test:e2e:debug
```

### View Report
```bash
npm run test:e2e:report
```

**Total: 18+ E2E tests**

---

## Full Test Suite

### Run Everything
```bash
# Terminal 1: Start backend
cd backend && poetry run python -m app.main

# Terminal 2: Start frontend
cd frontend && npm run dev

# Terminal 3: Run backend tests
cd backend && poetry run pytest

# Terminal 4: Run E2E tests
cd frontend && npm run test:e2e
```

---

## Test Coverage Summary

| Component | Tests | Type |
|-----------|-------|------|
| Backend API | 51 | Integration |
| Backend WebSocket | 11 | Integration |
| Backend Containers | 15 | Integration |
| Backend Database | 11 | Integration |
| **Backend Total** | **88** | **Integration** |
| Frontend Projects | 5 | E2E |
| Frontend Chat | 6 | E2E |
| Frontend Agent Config | 7 | E2E |
| **Frontend Total** | **18+** | **E2E** |
| **Grand Total** | **106+** | **All** |

---

## Common Commands

### Backend
```bash
# Install deps
poetry install

# Run tests
poetry run pytest

# With coverage
poetry run pytest --cov=app

# Skip slow tests
poetry run pytest -m "not slow"

# Parallel
poetry run pytest -n auto

# Stop on first failure
poetry run pytest -x

# Show output
poetry run pytest -s
```

### Frontend
```bash
# Install deps
npm install

# Run E2E
npm run test:e2e

# With UI
npm run test:e2e:ui

# Debug
npm run test:e2e:debug

# Specific browser
npm run test:e2e:chromium

# View report
npm run test:e2e:report
```

---

## Prerequisites

### Backend
- Python 3.13
- Poetry
- Docker Desktop (for container tests)

### Frontend
- Node.js 18+
- npm

---

## Documentation

- **Backend Tests**: `backend/tests/README.md`
- **Frontend Tests**: `frontend/tests/README.md`
- **Test Plan**: `TEST_PLAN.md`
- **Backend Summary**: `BACKEND_TESTS_SUMMARY.md`
- **Changes Summary**: `CHANGES_SUMMARY.md`

---

## Quick Troubleshooting

### Backend: "Docker not available"
```bash
# Start Docker Desktop
# Then run:
poetry run pytest -m "not container"  # Skip container tests
```

### Frontend: "Server not responding"
```bash
# Ensure backend is running
cd backend && poetry run python -m app.main

# Ensure frontend is running
cd frontend && npm run dev
```

### Tests hanging
```bash
# Backend: Add timeout
poetry run pytest --timeout=30

# Frontend: Check browser didn't open debugger
# Use headless mode:
npm run test:e2e
```

### Coverage not working
```bash
# Backend
poetry add --group dev pytest-cov
poetry run pytest --cov=app

# Frontend
npm install -D @vitest/coverage-v8
npm run test:coverage
```

---

## CI/CD Ready

All tests are configured for continuous integration:

- ✅ Automated test discovery
- ✅ Coverage reporting
- ✅ Parallel execution support
- ✅ Docker availability detection
- ✅ Proper cleanup/teardown

See `TEST_PLAN.md` section 7 for GitHub Actions examples.
