# Testing

## Overview

This directory contains test suites for both backend and frontend components.

## Structure

```
tests/
├── backend/        # Backend API tests
│   ├── conftest.py # Pytest configuration
│   └── test_*.py   # Test modules
└── frontend/       # Frontend component tests
    └── *.test.tsx  # Jest test files
```

## Running Tests

### Backend Tests

```bash
cd backend
source venv/bin/activate
pytest ../tests/backend/ -v
```

### Frontend Tests

```bash
cd frontend
npm test
```

### Coverage Reports

```bash
# Backend coverage
pytest --cov=app --cov-report=html

# Frontend coverage
npm test -- --coverage
```

## Test Categories

- **Unit Tests**: Individual function and component testing
- **Integration Tests**: API endpoint testing
- **Component Tests**: React component rendering and behavior

## Writing Tests

### Backend Test Example

```python
def test_api_endpoint(client):
    response = client.get("/api/v1/meetings/")
    assert response.status_code == 200
```

### Frontend Test Example

```typescript
test('renders component', () => {
  render(<Component />);
  expect(screen.getByText('Hello')).toBeInTheDocument();
});
```

## Continuous Integration

Tests are run automatically via GitHub Actions on pull requests and commits to main branch.

## Note

This is an archived project. Test suites are provided for reference.
