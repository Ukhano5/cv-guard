# 🧠 Smart AI CV Matcher — FYP Project

**BS Computer Science — Final Year Project**

An end-to-end AI-powered recruitment platform that accepts CVs (PDF/Image), extracts text using OCR, matches candidates to jobs using NLP/TF-IDF, and ranks them using a geographic location-based priority tier system.

---

## 🚀 Quick Start

```bash
# 1. Unzip the project
unzip cv_matcher.zip
cd cv_matcher

# 2. Run setup & launch
bash run.sh
```

Then open: **http://127.0.0.1:5000**

---

## 🔐 Default Login Credentials

| Role  | Email                   | Password  |
|-------|-------------------------|-----------|
| Admin | admin@cvmatcher.com     | admin123  |
| User  | Register a new account  | (your choice) |

---

## 📁 Project Structure

```
cv_matcher/
├── app.py              ← Main Flask application (routes, logic)
├── models.py           ← SQLAlchemy DB models (User, Job, Application)
├── ai_engine.py        ← AI: OCR, TF-IDF matching, location tier logic
├── filters.py          ← Jinja2 custom template filters
├── requirements.txt    ← Python dependencies
├── run.sh              ← One-click setup and launch script
├── instance/
│   └── cv_matcher.db   ← SQLite database (auto-created)
├── static/
│   └── uploads/        ← Uploaded CV files stored here
└── templates/
    ├── login.html              ← Login page (Admin + User roles)
    ├── register.html           ← User registration
    ├── admin_dashboard.html    ← Admin: stats, job management
    ├── admin_applications.html ← Admin: ranked CV viewer per job
    ├── admin_users.html        ← Admin: user management
    ├── user_dashboard.html     ← User: job board + apply + chatbot
    └── my_applications.html    ← User: application history & scores
```

---

## ✨ Features

### 🔑 Authentication
- Secure login/signup with hashed passwords (Werkzeug)
- Role-based access: Admin vs Job Seeker
- Session management with Flask-Login
- Flash messages for all errors and successes

### 🏢 Admin Panel
- **Dashboard** with live stats (total jobs, users, applications)
- **Post Jobs** with title, description, required skills, location, deadline
- **Delete Jobs** (with all associated applications)
- **View Applications** per job — ranked and sorted
- **Top 3 Picks** highlighted with reasoning (why eligible)
- **User Management** — view and delete candidates
- Location-based color coding for candidates

### 💼 Job Seeker (User Panel)
- **Job Board** — beautiful card grid with search/filter
- **Apply with CV** — drag & drop or click to upload (PDF/PNG/JPG)
- **Real-time AI Assessment** — animated progress bar showing:
  - Text extraction → AI matching → Score calculation
- **Results Panel** showing:
  - Match Score (0–100%)
  - Eligibility Status (Passed ✓ / Not Eligible ✗)
  - Priority Tier Label (1/2/3)
  - Matched Skills List
- **My Applications** — full history with scores, tiers, matched skills
- **AI Chatbot Bubble** — answers questions about:
  - Available vacancies
  - Deadlines
  - How to apply
  - Location priority tiers
  - Application status

### 🤖 AI Engine
- **PDF extraction**: pdfplumber (multi-page support)
- **Image OCR**: pytesseract (Tesseract) with PIL
- **NLP Matching**: TF-IDF + Cosine Similarity (scikit-learn)
  - 60% semantic similarity weight
  - 40% keyword skill match weight
- **Eligibility threshold**: Score ≥ 30% = Eligible

### 📍 Location Priority System
| Tier | Cities | Priority |
|------|--------|----------|
| Tier 1 | Rawalpindi | Highest |
| Tier 2 | Islamabad, Jhelum, Peshawar, Attock, Taxila, Wah Cantt | Medium |
| Tier 3 | All other cities | Lowest |

Applications are ranked: Tier 1 first → then by match score descending.
Top 3 picks are highlighted with gold border and reasoning explanation.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, Tailwind CSS, Vanilla JS, Font Awesome |
| Backend | Python Flask |
| Database | SQLite (via SQLAlchemy ORM) |
| Auth | Flask-Login + Werkzeug password hashing |
| PDF OCR | pdfplumber |
| Image OCR | pytesseract + PIL |
| NLP | scikit-learn (TF-IDF + Cosine Similarity) |
| Animations | CSS keyframes, Tailwind transitions |

---

## ⚠️ Error Handling

- Wrong credentials → red flash alert
- Corrupt/empty CV → graceful error message (no server crash)
- Unsupported file type → validation before processing
- Network errors in upload → friendly UI error panel
- Missing city → defaults to Tier 3

---

## 📊 Demo Data

On first launch, 3 demo jobs are auto-created:
1. Python Developer (Rawalpindi)
2. UI/UX Designer (Islamabad)
3. Data Analyst (Lahore)

---

## 🎓 FYP Presentation Notes

This project demonstrates:
- **Full-stack web development** (Flask + SQL + HTML/CSS/JS)
- **AI/NLP integration** (TF-IDF, Cosine Similarity)
- **OCR processing** (PDF and Image text extraction)
- **Algorithm design** (location-based priority tiering)
- **Database design** (relational schema with SQLAlchemy)
- **UX design** (glassmorphism, animations, responsive layout)
- **Software engineering** (clean code, error handling, modular structure)
