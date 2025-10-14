# UI Changes for Update Checker Feature

## Menu Bar Changes

A new **Help** menu has been added to the menu bar with the "Check for Updates" option:

### Before (No Help Menu)
```
┌─────────────────────────────────────────────────────────────────┐
│ ZXLive                                                          │
├─────────────────────────────────────────────────────────────────┤
│ File │ Edit │ View │ Rewrite │                                  │
└─────────────────────────────────────────────────────────────────┘
```

### After (With Help Menu)
```
┌─────────────────────────────────────────────────────────────────┐
│ ZXLive                                                          │
├─────────────────────────────────────────────────────────────────┤
│ File │ Edit │ View │ Rewrite │ Help │                           │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    └─→ Check for Updates...
```

## Dialog Flows

### 1. Update Available Dialog

When an update is found (either automatically or manually), this dialog appears:

```
┌──────────────────────────────────────────────────┐
│  Update Available                            [X] │
├──────────────────────────────────────────────────┤
│  ℹ️                                              │
│  A new version of ZXLive is available!          │
│                                                  │
│  Current version: 0.3.1                         │
│  Latest version: 0.4.0                          │
│                                                  │
│  Visit the releases page to download the        │
│  latest version.                                │
│                                                  │
│                     [Later]  [View Release]     │
└──────────────────────────────────────────────────┘
```

**Actions:**
- **Later**: Closes the dialog without taking action
- **View Release**: Opens the GitHub releases page in the default browser

### 2. Checking for Updates Dialog (Manual Check)

When user clicks "Help → Check for Updates", a temporary dialog shows:

```
┌──────────────────────────────────────────────────┐
│  Checking for Updates                            │
├──────────────────────────────────────────────────┤
│                                                  │
│  Checking for updates...                        │
│                                                  │
└──────────────────────────────────────────────────┘
```

This dialog automatically closes once the check completes.

### 3. No Updates Dialog (Manual Check)

If no updates are found during a manual check:

```
┌──────────────────────────────────────────────────┐
│  No Updates                                  [X] │
├──────────────────────────────────────────────────┤
│  ℹ️                                              │
│  You are using the latest version of ZXLive!    │
│                                                  │
│                                         [OK]     │
└──────────────────────────────────────────────────┘
```

## Workflow Diagrams

### Automatic Check on Startup

```
┌─────────────┐
│ App Starts  │
└──────┬──────┘
       │
       ▼
┌──────────────────────┐     No      ┌──────────────┐
│ Last check > 24hrs?  ├────────────►│ Skip check   │
└──────┬───────────────┘             └──────────────┘
       │ Yes
       ▼
┌──────────────────────┐
│ Check in background  │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐     Yes     ┌──────────────────┐
│ Update available?    ├────────────►│ Show dialog      │
└──────┬───────────────┘             └──────────────────┘
       │ No
       ▼
┌──────────────────────┐
│ Update settings      │
│ (last-update-check)  │
└──────────────────────┘
```

### Manual Check

```
┌──────────────────────┐
│ User clicks Help →   │
│ Check for Updates    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Show "Checking..."   │
│ dialog               │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Check GitHub API     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐     Yes     ┌──────────────────┐
│ Update available?    ├────────────►│ Show update      │
└──────┬───────────────┘             │ dialog           │
       │ No                           └──────────────────┘
       ▼
┌──────────────────────┐
│ Show "No updates"    │
│ dialog               │
└──────────────────────┘
```

## User Experience Notes

1. **Non-intrusive**: Automatic checks happen silently in the background
2. **Fail-safe**: Network errors don't interrupt the user experience
3. **Throttled**: Checks limited to once per day to respect GitHub API
4. **User Control**: Manual check available anytime via Help menu
5. **Clear Action**: "View Release" button directly opens the download page

## Settings Storage

The feature stores one setting in QSettings:

| Key | Type | Description | Example Value |
|-----|------|-------------|---------------|
| `last-update-check` | string | ISO format timestamp of last check | `2025-10-14T18:45:23.123456` |

This setting is automatically managed by the application and doesn't require user configuration.
