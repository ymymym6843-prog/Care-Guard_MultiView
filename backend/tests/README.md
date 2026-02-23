# SENTIO Backend Tests

This directory contains unit tests for the SENTIO backend project.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── test_fall_detector.py    # Tests for fall detection service
├── test_alert_manager.py    # Tests for alert management service
├── test_auth.py             # Tests for authentication utilities
└── README.md                # This file
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test file
```bash
pytest tests/test_fall_detector.py
pytest tests/test_alert_manager.py
pytest tests/test_auth.py
```

### Run specific test class or function
```bash
pytest tests/test_fall_detector.py::TestFallDetector
pytest tests/test_fall_detector.py::TestFallDetector::test_normal_standing_pose_no_fall
```

### Run with coverage
```bash
pytest --cov=app --cov-report=html
```

### Run with verbose output
```bash
pytest -v
```

### Run tests matching a pattern
```bash
pytest -k "cooldown"
pytest -k "test_fall or test_alert"
```

## Test Coverage

### `test_fall_detector.py`
Tests for `app.services.fall_detector.FallDetector`:
- Normal standing pose detection
- Head below hip detection
- Rapid descent detection
- Horizontal body angle detection
- Composite score calculation
- 2-second cooldown behavior
- State reset after cooldown
- Per-person state tracking
- History management
- Edge cases (insufficient landmarks, etc.)

### `test_alert_manager.py`
Tests for `app.services.alert_manager.AlertManager`:
- Initial state management
- State transitions (normal → monitoring → warning → danger)
- Acknowledge functionality
- Normal pose reset behavior
- Per-person state tracking
- Global state management
- Event callbacks
- Frontend state mapping

### `test_auth.py`
Tests for `app.core.auth`:
- Password hashing (salted, secure)
- Password verification
- JWT token creation
- JWT token decoding
- Token validation
- Edge cases (special characters, unicode, etc.)

## Fixtures

### Available fixtures (from `conftest.py`)

- `mock_landmarks_standing`: Normal standing pose with 33 MediaPipe landmarks
- `mock_landmarks_fallen`: Fallen pose with head below hip

## Requirements

All test dependencies are in `requirements.txt`:
- pytest >= 7.4.0
- pytest-asyncio >= 0.23.0
- httpx >= 0.25.0 (for testing FastAPI endpoints, if needed)

## Writing New Tests

Follow the AAA pattern:
1. **Arrange**: Set up test data and conditions
2. **Act**: Execute the code being tested
3. **Assert**: Verify the results

Example:
```python
def test_example(self):
    # Arrange
    detector = FallDetector()

    # Act
    result = detector.detect(landmarks, person_id="test")

    # Assert
    assert result["is_fallen"] is False
```

## Notes

- Tests are isolated and don't require database setup
- Database-dependent functions (like `get_current_user`) are not tested here
- Use `pytest.mark.asyncio` for async tests
- Tests use mocking where appropriate to avoid external dependencies
