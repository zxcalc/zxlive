# Update Checker Feature

## Overview

ZXLive now includes an automatic update checker that checks for new releases from the GitHub repository. This feature helps users stay up-to-date with the latest improvements and bug fixes.

## Features

1. **Automatic Background Checks**: The application checks for updates once per day on startup
2. **Manual Check**: Users can manually check for updates via Help → Check for Updates menu
3. **Update Notifications**: When a new version is available, a dialog shows:
   - Current version
   - Latest available version
   - Link to the release page
4. **Smart Throttling**: Checks are limited to once per day to avoid excessive API calls

## Implementation Details

### Files Modified/Added:

1. **zxlive/update_checker.py** (NEW)
   - `UpdateCheckerWorker`: Worker thread for async update checking
   - `UpdateChecker`: Main manager class for update checks
   - Uses GitHub API to fetch latest release information
   - Compares versions using the `packaging` library

2. **zxlive/app.py**
   - Initializes update checker on application startup
   - Checks for updates in background if needed
   - Displays notification dialog when update is available

3. **zxlive/mainwindow.py**
   - Added Help menu with "Check for Updates" action
   - Implements `check_for_updates()` method for manual checks

4. **zxlive/dialogs.py**
   - Added `show_update_available_dialog()` function
   - Displays update information with link to release page

5. **pyproject.toml**
   - Added `packaging` dependency for version comparison

### Settings

The update checker stores the last check timestamp in QSettings:
- Key: `last-update-check`
- Value: ISO format datetime string

### API Usage

The feature uses GitHub's public API:
- Endpoint: `https://api.github.com/repos/zxcalc/zxlive/releases/latest`
- No authentication required
- Rate limited to once per day by the application

## User Experience

### Automatic Check (Background)
When a user starts ZXLive and it's been more than 24 hours since the last check:
1. Update check runs silently in background thread
2. If update available, dialog appears after startup
3. User can choose to "View Release" or dismiss with "Later"

### Manual Check
User can click Help → Check for Updates:
1. Shows "Checking for updates..." message
2. After check completes:
   - If update available: Shows update dialog
   - If no update: Shows "You are using the latest version" message

## Future Enhancements

Possible future improvements:
1. Add preference to disable automatic checks
2. Implement auto-update functionality (download and install)
3. Show release notes in the update dialog
4. Support checking for pre-release versions
