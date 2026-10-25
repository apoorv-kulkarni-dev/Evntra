# ✦ Eventora — Python Full-Stack Event Experience Platform

**Eventora** is a complete, self-contained Python web application for event discovery, ticket issuance with QR codes, and end-to-end organizer management.

Built with Python and a modern, high-converting front-end featuring luxury glassmorphism, dark/light theme modes, audio feedback, and micro-interactions.

---

## 🚀 Quick Start (One Command)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python app.py
```

Then open your browser to:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🌟 Key Features

### 🌐 1. Public Event Discovery (Attendees)
- **Visual Event Showcase**: High-resolution banners, dates, venue tags, ticket price indicators (*Free* or *₹1,499*), and seat capacity progress bars.
- **Real-Time Search & Filtering**: Instant search by keywords and filter by categories (*Tech & AI, Music & Sound, Business & VC, Design*).
- **Instant Digital Boarding Pass**: Attendees register in seconds and receive an authentic digital pass with an embedded QR code, seat info, and printable layout.
- **Canvas Confetti & Audio Chimes**: Celebration confetti upon booking and tactile Web Audio API feedback.

### 📊 2. Organizer Studio (Event Directors)
- **⚡ 1-Click Demo Organizer Login**: Click **"Try Demo Organizer"** in the top navigation bar to access the full organizer workspace as `Aarav Sharma` (`organizer@eventora.io`) without typing credentials.
- **Executive Analytics Overview**: Real-time KPI summary cards (Active Events, Registrations, Attendance Check-in %, Budget vs. Spend).
- **QR Check-in Station & Scanner Simulator**: Live attendee check-in desk with real-time search, 1-click check-in with timestamps, and a simulated laser scanner.
- **Kanban Tasks Board**: 3-column workflow (`To Do`, `In Progress`, `Completed`) with priority tags and assignee tracking.
- **Run-of-Show Checklist**: Milestone checklist with live completion counters.
- **Guest RSVP Hub**: Manage guest invitations, track RSVP states (`Accepted`, `Pending`, `Declined`), and copy instant invitation links.
- **Budget & Financials**: Visual expense tracking, budget consumption gauges, and remaining balance calculations.
- **One-Click CSV Reports**: Export full event analytics to spreadsheet-ready `.csv` files.
- **Real-Time Notifications Feed**: Live updates for ticket registrations, gate check-ins, and budget thresholds.
- **Theme Switcher**: Smooth transition between Obsidian Dark mode and Modern Light mode.

---

## 📂 Project Structure

```
eventora-fullstack/
├── app.py                 # Core Python Web Server & REST API (Bottle)
├── database.py            # SQLite database schema, cryptographic hashing & seed data
├── eventora.db            # SQLite persistent database (auto-created & pre-seeded)
├── requirements.txt       # Python package dependencies
├── templates/
│   └── index.html         # Luxury responsive SPA interface (Lucide icons, QRCode generator)
├── static/
│   ├── css/
│   │   └── style.css      # Luxury glassmorphism design system
│   ├── js/
│   │   └── app.js         # Interactive application logic & audio synthesizer
│   └── images/            # High-resolution generated event banners
│       ├── ai_summit.jpg
│       ├── music_festival.jpg
│       └── founders_gala.jpg
```

---

## 🔐 Demo Credentials
- **Role**: Event Director & Organizer
- **Email**: `organizer@eventora.io`
- **Password**: `Password123!@#`
*(Or simply click **"Try Demo Organizer"** in the top navigation bar)*
