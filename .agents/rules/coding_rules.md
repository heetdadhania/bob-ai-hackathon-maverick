# Global Coding Rules

All code generated and modified in this workspace must strictly adhere to the following rules:

1. **No hardcoded values**: API keys, DB URLs, file paths, and magic numbers must go through `.env` or a dedicated configuration module (`config.py`), never inline.
2. **No dead or unused code**: No unused imports, functions, or variables. Every function written must be actively used or called.
3. **No mocked or fake outputs pretending to be real**: Predictions, rankings, and generated plans must be genuinely computed from the pipeline, not hardcoded example strings.
4. **Consistent naming**: Use `snake_case` for Python. Use `asset_id` consistently as the join key across every file, dataset, and database table.
5. **Error handling on all I/O**: DB connections, HTTP calls (watsonx/Bob, Open-Meteo, etc.) must be wrapped in `try/except` blocks with meaningful error messages; never use silent failures or bare `pass`.
6. **Judicious docstrings**: Docstrings only where logic is non-obvious (e.g., degradation functions, ranking formulas), not on every trivial getter/setter or obvious function.
7. **No print-debugging**: Use Python's standard `logging` module instead of `print` statements.
8. **Type hints**: Comprehensive type hints on all function signatures.
9. **Single responsibility per file**: Each script/module does one distinct job.
10. **PEP8 formatting**: Follow PEP8 standards with ~88-100 character line length.
11. **Config centralization**: One `.env`/config source per module; no scattered constants.
12. **No commented-out code**: Delete unused code blocks rather than leaving commented-out code.
13. **Reproducibility**: Set `np.random.seed(42)` (or equivalent random seed) wherever randomness is used in data generation, splitting, or model training.
14. **Meaningful names**: Descriptive variable and function names; avoid ambiguous short names like `df1`, `temp2`, or `x`.
15. **Input validation**: Validate inputs at function boundaries (e.g., verify expected columns/data types before feeding data to models or pipelines).
16. **Short, focused functions**: Split functions that perform 3+ distinct operations into smaller, dedicated functions.
17. **Separate logic from execution glue**: Expose modular, importable, and unit-testable functions rather than top-to-bottom procedural script execution.
18. **Pin exact versions**: Pin exact dependency versions in `requirements.txt`.
19. **No silent fallbacks**: Surface failures clearly (e.g., if a watsonx or external API call fails, raise/log the error clearly rather than secretly returning a canned fallback).
20. **Consistent ISO 8601 formatting**: Standardize date/time strings to ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ` or with timezone offset) across all data sources and interfaces.
