# PillTracker

PillTracker is a desktop application for tracking pill schedules, medication reminders, and supplement timing. Built with a focus on clarity and usability, it helps users manage recurring doses with configurable intervals, themes, and clock display modes.

## ✨ Features

- **Medication Schedule Tracking**: Track multiple pills or supplements with custom reminder intervals (in minutes).
- **Beautiful Qt Interface**: Features modern, card-style components and a responsive layout.
- **Customizable Appearance**: Adjustable font sizes, theme selection, and custom color settings.
- **Clock Widgets**: Support for both analog and digital clock displays.
- **Persistent Storage**: Settings are saved automatically to `settings.json`.
- **Activity Logging**: Maintains a `pill_log.txt` to keep track of medication history.

## 📦 Project Details

| Property | Value |
| :--- | :--- |
| **App Name** | PillTracker |
| **Author** | Mandy & Hobab |
| **Version** | 2.2.0 |

## 🧠 Application Overview

PillTracker manages a list of medications and their respective timing intervals. It provides a visual dashboard to see when the next dose is due. The codebase includes modular logic for:

- Log parsing and management.
- Time and status calculations.
- UI theme/color helper functions.
- Dynamic widget generation (Card, AnalogClock).

## 🗂️ Data Storage

The application stores user preferences and logs in the local user configuration directory:

- **Settings**: `settings.json` (Stores UI preferences, themes, and the list of pills).
- **Logs**: `pill_log.txt` (Maintains historical data).

## 🛠️ Installation & Setup

1. **Clone the repository**:
```bash
   git clone https://github.com/NarimanE3D/pill-tracker
   cd PillTracker/built
   ./PillTracker-Setup-2.2.0.exe
```
