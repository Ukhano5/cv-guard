# CV Guard

An AI-powered recruitment platform that intelligently matches candidate CVs to job descriptions using NLP-based similarity scoring and OCR-driven document parsing.

## Overview

CV Guard streamlines the recruitment screening process by automatically extracting, parsing, and scoring resumes against job requirements. It combines semantic text analysis with keyword matching to produce a weighted relevance score, helping recruiters quickly identify the best-fit candidates without manually reading every CV.

## Features

- **Automated CV Parsing** — Extracts text from PDF and scanned/image-based resumes using OCR
- **Intelligent Matching** — Scores candidates against job descriptions using a hybrid similarity model (60% semantic, 40% keyword-based)
- **Role-Based Access** — Separate flows for recruiters/admins and applicants
- **Application Dashboard** — Track and manage submitted applications in one place
- **User Settings & Management** — Admin-level user controls and profile management

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask (Python) |
| Matching Engine | TF-IDF + Cosine Similarity |
| OCR | Tesseract, EasyOCR |
| PDF Parsing | pdfplumber |
| Database | SQLAlchemy (SQLite) |
| Frontend | Tailwind CSS |

## How It Works

1. A candidate uploads their CV (PDF or scanned image)
2. The system extracts raw text using `pdfplumber` for digital PDFs, falling back to OCR (Tesseract/EasyOCR) for scanned documents
3. Extracted text is cleaned and compared against the job description using TF-IDF vectorization and cosine similarity
4. A final match score is calculated using a weighted blend of semantic similarity (60%) and keyword overlap (40%)
5. Recruiters view ranked candidates through the admin dashboard

## Getting Started

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/Ukhano5/cv-guard.git
cd cv-guard

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
python app.py
```

The app will start on `http://localhost:5000` (or the port configured in `app.py`).

## Project Structure

```
cv_matcher/
├── app.py              # Main application entry point
├── ai_engine.py         # Matching/scoring logic
├── filters.py           # Preprocessing and filtering utilities
├── models.py             # Database models
├── static/               # CSS/JS/static assets
├── templates/             # HTML templates
└── requirements.txt        # Python dependencies
```
USER PANEL
 <img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/4cdc5efa-53a7-46c4-8a92-0b92dd81d725" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/a681f6cd-6249-426f-b81f-b217099f9f9b" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/6a0bec48-7b2c-4a79-8728-485975c3370a" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/59cef393-0d5f-42d0-b43d-cc7c161ed580" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/09db7a08-d54d-4f02-bd78-3fb9438e704b" />

ADMIN PANEL
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/dd4509cc-d48f-46c1-8573-2934598562cf" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/379dad19-20a9-49ea-97ea-78bb608bed65" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/7ba1cdef-ec8a-4447-b8ac-ed80ddc13ae3" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/823c115e-74f1-4482-96f7-64eebb5d1956" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/7f00ab3c-6bb8-4b29-aec3-1bbd8757d985" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/e7e8bdd2-3156-497f-ba61-7b68e8e2e110" />
<img width="1366" height="768" alt="image" src="https://github.com/user-attachments/assets/ca7349a2-a606-4457-a171-70e7e2e00ec5" />



## Roadmap

- [ ] Add live demo deployment
- [ ] Support for additional file formats (DOCX)
- [ ] Improved ranking with configurable scoring weights
- [ ] Export shortlisted candidates to CSV/PDF

## License

This project is available under the MIT License.
