# GitHub Pages Setup

This document explains how to enable GitHub Pages for the YSimulator documentation.

## Overview

The documentation is built using MkDocs with the Material theme and automatically deployed to GitHub Pages via GitHub Actions. The workflow is defined in `.github/workflows/docs.yml`.

## Prerequisites

- Repository admin access
- GitHub Pages feature available for your repository

## Setup Instructions

### 1. Enable GitHub Pages

1. Navigate to your repository on GitHub
2. Go to **Settings** > **Pages** (in the left sidebar)
3. Under **Source**, select:
   - **Source**: GitHub Actions

That's it! GitHub Actions will now automatically build and deploy the documentation.

### 2. Verify Deployment

After enabling GitHub Pages:

1. Push changes to the `main` branch that affect documentation (any file in `docs/`, `mkdocs.yml`, or `.github/workflows/docs.yml`)
2. Go to the **Actions** tab in your repository
3. Look for the "Deploy MkDocs Documentation" workflow
4. Wait for it to complete successfully
5. Your documentation will be available at: `https://ysocialtwin.github.io/YSimulator/`

## Workflow Details

### Trigger Events

The documentation workflow is triggered by:

- **Push to main branch** when changes affect:
  - Files in the `docs/` directory
  - The `mkdocs.yml` configuration file
  - The workflow file itself (`.github/workflows/docs.yml`)
- **Manual trigger** via the "workflow_dispatch" event (accessible from the Actions tab)

### Build Process

The workflow performs these steps:

1. **Checkout code**: Gets the latest code from the repository
2. **Setup Python**: Installs Python 3.11
3. **Install dependencies**: Installs MkDocs, Material theme, and extensions
4. **Build site**: Generates static HTML from Markdown files
5. **Upload artifact**: Packages the built site for deployment
6. **Deploy**: Publishes the site to GitHub Pages

## Local Development

### Build Locally

To build and preview the documentation locally:

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Build the documentation
mkdocs build

# Serve locally with live reload
mkdocs serve
```

Then open your browser to `http://127.0.0.1:8000/`

### MkDocs Commands

- `mkdocs build`: Build the static site to the `site/` directory
- `mkdocs serve`: Start local development server with live reload
- `mkdocs build --clean`: Clean build (removes old files first)
- `mkdocs gh-deploy`: Manually deploy to GitHub Pages (not needed with our GitHub Actions workflow)

## Configuration

The documentation is configured in `mkdocs.yml`:

- **Site metadata**: Name, description, URL
- **Theme settings**: Material theme with dark/light mode
- **Navigation**: Sidebar structure and page organization
- **Extensions**: Markdown extensions for features like code highlighting, admonitions, etc.

## Updating Documentation

To update the documentation:

1. Edit markdown files in the `docs/` directory
2. Commit and push to `main` branch
3. GitHub Actions will automatically rebuild and deploy

## Troubleshooting

### Documentation Not Updating

1. Check the Actions tab for workflow status
2. Look for errors in the "Deploy MkDocs Documentation" workflow
3. Ensure GitHub Pages is set to use "GitHub Actions" as the source

### Build Failures

1. Check that all referenced files in `mkdocs.yml` exist in the `docs/` directory
2. Verify markdown syntax is valid
3. Test locally with `mkdocs build` to see detailed error messages

### 404 Errors

1. Check that the page exists in the `nav` section of `mkdocs.yml`
2. Verify relative links use the correct paths
3. Ensure the site URL in `mkdocs.yml` matches your GitHub Pages URL

## Adding New Pages

To add new documentation pages:

1. Create a new `.md` file in the appropriate `docs/` subdirectory
2. Add the page to the `nav` section in `mkdocs.yml`:

```yaml
nav:
  - Section Name:
    - Page Title: path/to/file.md
```

3. Commit and push to trigger automatic deployment

## Dependencies

The documentation build requires:

- `mkdocs>=1.5.0,<2.0.0` - Core MkDocs
- `mkdocs-material>=9.0.0,<10.0.0` - Material theme
- `pymdown-extensions>=10.0.0,<11.0.0` - Markdown extensions

These are listed in `requirements-dev.txt`.
