import os
import re
import json

# ─── PROXIMITY MAP ─────────────────────────────────────────────────────────────
# For each city, define which cities are "nearby" (Tier 2 when that city is the job location)
# This is bidirectional — if A is near B, B is near A
NEARBY = {
    'rawalpindi': ['islamabad', 'taxila', 'wah cantt', 'attock', 'chakwal', 'jhelum', 'murree', 'kahuta', 'gujar khan'],
    'islamabad':  ['rawalpindi', 'taxila', 'wah cantt', 'attock', 'murree', 'kahuta'],
    'lahore':     ['sheikhupura', 'kasur', 'nankana sahib', 'gujranwala', 'okara', 'sahiwal', 'sialkot', 'gujrat', 'narowal'],
    'karachi':    ['hyderabad', 'thatta', 'badin', 'mirpur khas', 'matiari'],
    'peshawar':   ['nowshera', 'charsadda', 'mardan', 'swabi', 'attock', 'kohat'],
    'quetta':     ['pishin', 'mastung', 'kalat', 'hub', 'chaman'],
    'faisalabad': ['jhang', 'chiniot', 'toba tek singh', 'gojra', 'sargodha'],
    'multan':     ['bahawalpur', 'khanewal', 'lodhran', 'muzaffargarh', 'vehari', 'sahiwal'],
    'hyderabad':  ['karachi', 'matiari', 'tando allahyar', 'badin', 'jamshoro'],
    'gujranwala': ['lahore', 'sialkot', 'gujrat', 'hafizabad', 'narowal', 'sheikhupura'],
    'sialkot':    ['gujranwala', 'gujrat', 'lahore', 'narowal', 'daska'],
    'abbottabad': ['mansehra', 'haripur', 'havelian', 'murree', 'islamabad'],
    'jhelum':     ['rawalpindi', 'chakwal', 'gujrat', 'kharian'],
    'attock':     ['rawalpindi', 'islamabad', 'taxila', 'peshawar', 'nowshera', 'wah cantt'],
    'taxila':     ['rawalpindi', 'islamabad', 'wah cantt', 'attock', 'hasan abdal'],
    'mardan':     ['peshawar', 'swabi', 'charsadda', 'nowshera'],
    'sukkur':     ['larkana', 'khairpur', 'shikarpur', 'jacobabad'],
    'larkana':    ['sukkur', 'shikarpur', 'jacobabad', 'kambar'],
    'muzaffarabad': ['rawalakot', 'mirpur', 'bagh', 'islamabad'],
    'mirpur':     ['muzaffarabad', 'jhelum', 'rawalpindi', 'kotli'],
    'gilgit':     ['skardu', 'hunza', 'ghizer', 'chilas'],
    'skardu':     ['gilgit', 'hunza', 'ghanche', 'astore'],
    # International
    'dubai':      ['abu dhabi', 'sharjah', 'ajman', 'al ain'],
    'abu dhabi':  ['dubai', 'al ain', 'sharjah'],
    'riyadh':     ['kharj', 'dawadmi', 'diriyah'],
    'jeddah':     ['mecca', 'taif', 'yanbu'],
    'london':     ['birmingham', 'manchester', 'oxford', 'cambridge', 'bristol', 'coventry'],
    'manchester': ['london', 'leeds', 'sheffield', 'liverpool', 'chester'],
    'new york city': ['newark', 'jersey city', 'brooklyn', 'bronx', 'yonkers'],
    'toronto':    ['mississauga', 'brampton', 'hamilton', 'markham', 'vaughan'],
    'sydney':     ['newcastle', 'wollongong', 'canberra', 'parramatta'],
    'melbourne':  ['geelong', 'ballarat', 'bendigo', 'frankston'],
}

def get_nearby_cities(job_city: str) -> list:
    """Return list of nearby cities for a given job city."""
    city_lower = job_city.lower().strip()
    # Direct lookup
    if city_lower in NEARBY:
        return NEARBY[city_lower]
    # Partial match (e.g. 'rawalpindi city' -> 'rawalpindi')
    for key in NEARBY:
        if key in city_lower or city_lower in key:
            return NEARBY[key]
    return []

def get_location_tier(user_city: str, job_location: str) -> int:
    """
    Dynamic tier system:
      Tier 1 = user city matches job city exactly
      Tier 2 = user city is in the nearby list for that job city
      Tier 3 = everything else
    """
    user = (user_city or '').lower().strip()
    job  = (job_location or '').lower().strip()

    if not user or not job:
        return 3

    # Tier 1 — exact or substring match (handles 'rawalpindi city' vs 'rawalpindi')
    if user == job or user in job or job in user:
        return 1

    # Tier 2 — nearby cities for this specific job location
    nearby = get_nearby_cities(job)
    for near in nearby:
        if near in user or user in near:
            return 2

    # Tier 3 — everything else
    return 3


# ─── TEXT EXTRACTION ───────────────────────────────────────────────────────────

def extract_text_from_file(filepath: str) -> str:
    ext = filepath.rsplit('.', 1)[-1].lower()
    text = ''
    if ext == 'pdf':
        text = _extract_from_pdf(filepath)
    elif ext in ('png', 'jpg', 'jpeg'):
        text = _extract_from_image(filepath)
    return text.strip()

def _extract_from_pdf(filepath: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            pages_text = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
            return '\n'.join(pages_text)
    except Exception:
        return ''

def _extract_from_image(filepath: str) -> str:
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(filepath)
        return pytesseract.image_to_string(img)
    except Exception:
        try:
            import easyocr
            reader = easyocr.Reader(['en'], gpu=False)
            result = reader.readtext(filepath, detail=0)
            return ' '.join(result)
        except Exception:
            return ''


# ─── CV MATCHING ───────────────────────────────────────────────────────────────

def match_cv_to_job(cv_text: str, job_description: str, required_skills_str: str):
    """Returns (score: float 0-100, matched_skills: list)"""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return _simple_keyword_match(cv_text, required_skills_str)

    required_skills = [s.strip().lower() for s in required_skills_str.split(',') if s.strip()]
    cv_lower = cv_text.lower()
    matched_skills = [skill for skill in required_skills if skill in cv_lower]

    try:
        combined_job = job_description + ' ' + required_skills_str
        vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform([cv_text, combined_job])
        semantic_score = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]) * 100
    except Exception:
        semantic_score = 0.0

    skill_score = (len(matched_skills) / len(required_skills) * 100) if required_skills else 0.0
    final_score = float(min(100, max(0, (semantic_score * 0.6) + (skill_score * 0.4))))
    return final_score, matched_skills

def _simple_keyword_match(cv_text: str, required_skills_str: str):
    required_skills = [s.strip().lower() for s in required_skills_str.split(',') if s.strip()]
    cv_lower = cv_text.lower()
    matched = [s for s in required_skills if s in cv_lower]
    return float((len(matched) / len(required_skills) * 100) if required_skills else 0.0), matched


# ─── RANKING ───────────────────────────────────────────────────────────────────

def rank_applications(applications):
    """Sort by tier (asc) then score (desc), annotate rank + top3"""
    sorted_apps = sorted(applications, key=lambda a: (a.priority_tier, -a.match_score))
    for i, app in enumerate(sorted_apps):
        app.rank = i + 1
        app.is_top3 = i < 3
        try:
            app.skills_list = json.loads(app.matched_skills or '[]')
        except Exception:
            app.skills_list = []
    return sorted_apps
