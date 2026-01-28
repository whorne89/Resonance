# Versioning Guide for Resonance

This document explains how versioning works for the Resonance project.

## Semantic Versioning

Resonance follows [Semantic Versioning 2.0.0](https://semver.org/):

**MAJOR.MINOR.PATCH** (e.g., 1.2.3)

- **MAJOR**: Incompatible API changes or major feature overhauls
- **MINOR**: New features added in a backwards-compatible manner
- **PATCH**: Backwards-compatible bug fixes

## Current Version

**v1.1.1** (January 28, 2026)

## How to Release a New Version

### 1. Update Version Numbers

Update the version in these files:
- `src/utils/config.py` - Line 50: `"version": "X.Y.Z"`
- `src/gui/system_tray.py` - Line 177: `"Version X.Y.Z"`

### 2. Update CHANGELOG.md

Add your changes under the appropriate category:
- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Features that will be removed soon
- **Removed**: Features that were removed
- **Fixed**: Bug fixes
- **Security**: Security-related changes

Example:
```markdown
## [1.2.0] - 2026-01-20

### Added
- New feature description

### Fixed
- Bug fix description
```

### 3. Commit and Tag

```bash
# Commit the version changes
git add -A
git commit -m "Release vX.Y.Z - Brief description"

# Create annotated tag
git tag -a vX.Y.Z -m "Release vX.Y.Z - Description of major changes"

# Push to GitHub
git push origin main
git push origin --tags
```

### 4. Create GitHub Release (Optional)

1. Go to https://github.com/whorne89/Resonance/releases
2. Click "Draft a new release"
3. Select the tag you just created
4. Copy the changelog section for this version
5. Publish the release

## Version History

- **v1.1.1** (2026-01-28): Fixed bundled EXE build issues (transcription, paths, branding)
- **v1.1.0** (2026-01-18): Feature improvements and bug fixes
- **v1.0.0** (2026-01-18): Initial release

## When to Bump Which Number

### MAJOR (X.0.0)
- Remove features that users depend on
- Change core functionality in incompatible ways
- Major architecture overhaul

### MINOR (1.X.0)
- Add new features (typing method settings, new dialogs, etc.)
- Add new configuration options
- Improve existing features significantly
- Add new menu items or UI elements

### PATCH (1.1.X)
- Fix bugs
- Improve performance
- Update documentation
- Refactor code without changing behavior
- Fix typos or UI text
