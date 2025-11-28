# Typhoon OCR E2E Tests

End-to-end tests for the typhoon-ocr package that validate OCR functionality on real images.

## Test Coverage

- **Main Test**: Validates OCR extraction of "SCBX", "AI", and "ปี" from `examples/test.png`
- **Task Types**: Tests all OCR task types (`v1.5`, `default`, `structure`)
- **API Integration**: Validates complete API workflow with real requests

## Requirements

Tests require valid API credentials set in environment variables:
- `OPENAI_API_KEY` or `TYPHOON_API_KEY` or `TYPHOON_OCR_API_KEY`
- `TYPHOON_BASE_URL` (optional, defaults to https://api.opentyphoon.ai/v1)

## Running Tests

```bash
# Set API credentials and run tests
OPENAI_API_KEY=your_key pytest tests/test_e2e_ocr.py -v

# Or use .env file with credentials
pytest tests/test_e2e_ocr.py -v
```

## Test Files

- `test_e2e_ocr.py` - Main e2e test suite with OCR validation

## Notes

- Tests enforce API key requirements and will fail without credentials
- Uses `examples/test.png` as test image (must exist)
- Validates both English and Thai text extraction
- Tests take ~20-30 seconds to complete due to API calls
