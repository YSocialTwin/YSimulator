# Pre-commit Hook Setup

This repository includes a pre-commit hook that automatically formats Python code using `black` and `isort`.

## Installation

The pre-commit hook is already installed in `.git/hooks/pre-commit`.

Install the required formatting tools:

```bash
pip install black isort
```

## Usage

The hook runs automatically on every commit. It will:

1. Format all staged Python files with `isort` (import sorting)
2. Format all staged Python files with `black` (code formatting)
3. Re-stage the formatted files

If formatting is applied, the files are automatically added back to the commit.

## Configuration

Formatting rules are defined in `pyproject.toml`:

- Line length: 100 characters
- Black profile for isort
- Python 3.8+ target

## Manual Formatting

To manually format files:

```bash
# Format specific files
python3 -m isort file.py
python3 -m black file.py

# Format all Python files in directory
python3 -m isort .
python3 -m black .
```
