# Code Formatting and Pre-commit Hooks

This repository uses automated code formatting and linting to maintain code quality and consistency.

## Pre-commit Framework

We use the [pre-commit](https://pre-commit.com/) framework to automatically run formatters and linters before each commit.

### Installation

1. Install development dependencies (includes pre-commit):

```bash
pip install -r requirements-dev.txt
```

2. Install the pre-commit hooks:

```bash
pre-commit install
```

This will set up the git hooks to run automatically on every commit.

### What Gets Checked

The pre-commit hooks will automatically:

1. **Format code with Black** - Consistent Python code formatting
2. **Sort imports with isort** - Organized import statements
3. **Lint with flake8** - Check for code quality issues
4. **Remove trailing whitespace** - Clean up unnecessary whitespace
5. **Fix line endings** - Ensure consistent line endings (LF)
6. **Check YAML files** - Validate YAML syntax
7. **Check for large files** - Prevent committing large files (>1MB)
8. **Check for merge conflicts** - Detect unresolved merge markers

If any hook fails, the commit will be aborted and you'll need to fix the issues and try again. In most cases, the hooks will automatically fix the files (formatting, whitespace, etc.), and you just need to stage the changes and commit again.

## Configuration

Formatting and linting rules are defined in:

- **`pyproject.toml`** - Black and isort configuration
  - Line length: 100 characters
  - Black profile for isort compatibility
  - Python 3.8+ target
  
- **`.flake8`** - Flake8 linting rules
  - Max line length: 130 characters
  - Ignores E203, E127, E402, W503 (Black compatibility)

- **`.pre-commit-config.yaml`** - Pre-commit hooks configuration

## Manual Formatting

To manually run all pre-commit hooks without committing:

```bash
pre-commit run --all-files
```

To format specific files manually:

```bash
# Format with isort
isort path/to/file.py

# Format with black
black path/to/file.py

# Run both
isort path/to/file.py && black path/to/file.py
```

To format all Python files in the repository:

```bash
# Sort imports
isort .

# Format code
black .
```

## Skipping Hooks (Not Recommended)

In rare cases where you need to bypass the hooks:

```bash
git commit --no-verify
```

**Note:** This should only be used in exceptional circumstances, as it bypasses all code quality checks.

## Updating Pre-commit Hooks

To update the pre-commit hooks to their latest versions:

```bash
pre-commit autoupdate
```

This will update the hook versions in `.pre-commit-config.yaml`.

## Troubleshooting

### Hooks not running

If the hooks aren't running, make sure they're installed:

```bash
pre-commit install
```

### Hook fails repeatedly

If a hook keeps failing:

1. Run it manually to see the full error:
   ```bash
   pre-commit run <hook-id> --all-files
   ```

2. Fix the issues manually

3. Try committing again

### Clean up hook cache

If you encounter issues with cached hook data:

```bash
pre-commit clean
pre-commit install --install-hooks
```
