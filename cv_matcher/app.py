from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os, json, re
from datetime import datetime
from models import db, User, Job, Application, Notification, Category, Setting
from ai_engine import extract_text_from_file, match_cv_to_job, get_location_tier, rank_applications
from filters import register_filters

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cvguard_secret_2024_fyp'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cvguard.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

db.init_app(app)
register_filters(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ─── HTML → PLAIN TEXT UTILITY ─────────────────────────────────────────────────
def html_to_plain(html: str) -> str:
    """Convert HTML message to fully clean readable plain text. No tags. No entities."""
    t = str(html)
    # Block tags → newlines
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</p>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<li\s*/?>', '• ', t, flags=re.IGNORECASE)
    t = re.sub(r'</li>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<ul[^>]*>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</ul>', '\n', t, flags=re.IGNORECASE)
    # Inline tags → keep their text content
    for tag in ['strong', 'b', 'em', 'i', 'u', 'span', 'div', 'p', 'h1', 'h2', 'h3']:
        t = re.sub(rf'<{tag}[^>]*>(.*?)</{tag}>', r'\1',
                   t, flags=re.IGNORECASE | re.DOTALL)
    # Strip any remaining tags
    t = re.sub(r'<[^>]+>', '', t)
    # Decode HTML entities
    for ent, char in [('&amp;','&'),('&lt;','<'),('&gt;','>'),
                      ('&quot;','"'),('&#39;',"'"),('&#34;','"'),
                      ('&#x27;',"'"),('&nbsp;',' ')]:
        t = t.replace(ent, char)
    # Clean lines
    lines = [l.strip() for l in t.split('\n')]
    lines = [l for l in lines if l]
    return '\n'.join(lines)

def enrich_notifs(notifs):
    """Add .preview (short clean text) to each notification for template use."""
    for n in notifs:
        full_plain = html_to_plain(n.message)
        # First 80 chars of first line as preview
        first_line = full_plain.split('\n')[0] if full_plain else ''
        n.preview = (first_line[:80] + '...') if len(first_line) > 80 else first_line
    return notifs

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def allowed_file(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_setting(key, default=''):
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else default

def set_setting(key, value):
    s = Setting.query.filter_by(key=key).first()
    if s: s.value = value
    else: db.session.add(Setting(key=key, value=value))
    db.session.commit()

def push_notification(user_id, title, message, notif_type='info'):
    n = Notification(user_id=user_id, title=title, message=message, notif_type=notif_type)
    db.session.add(n)
    db.session.commit()

def get_eligibility_threshold():
    return float(get_setting('eligibility_threshold', '30'))

# ─── AUTH ──────────────────────────────────────────────────────────────────────
@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard') if current_user.is_admin else url_for('user_dashboard'))
    if request.method == 'POST':
        email = request.form.get('email','').strip()
        password = request.form.get('password','').strip()
        role = request.form.get('role','user')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            if role == 'admin' and not user.is_admin:
                flash('Admin access denied.', 'error'); return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('admin_dashboard') if user.is_admin else url_for('user_dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip()
        password = request.form.get('password','').strip()
        city = request.form.get('city','').strip()
        if not all([name, email, password]):
            flash('All fields are required.', 'error'); return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error'); return redirect(url_for('register'))
        user = User(name=name, email=email, password_hash=generate_password_hash(password), city=city, is_admin=False)
        db.session.add(user); db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('login'))

# ─── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin: return redirect(url_for('user_dashboard'))
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    categories = Category.query.all()
    unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    notifs = enrich_notifs(Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all())
    threshold = get_eligibility_threshold()
    return render_template('admin_dashboard.html',
        jobs=jobs, categories=categories,
        total_users=User.query.filter_by(is_admin=False).count(),
        total_apps=Application.query.count(),
        total_jobs=Job.query.count(),
        eligible_count=Application.query.filter_by(is_eligible=True).count(),
        unread_notifs=unread_notifs, notifs=notifs, threshold=threshold)

@app.route('/admin/post_job', methods=['POST'])
@login_required
def post_job():
    if not current_user.is_admin: abort(403)
    title = request.form.get('title','').strip()
    description = request.form.get('description','').strip()
    skills = request.form.get('skills','').strip()
    location = request.form.get('location','').strip()
    deadline = request.form.get('deadline','').strip()
    category_id = request.form.get('category_id') or None
    if not all([title, description, skills, location]):
        flash('All fields required.', 'error'); return redirect(url_for('admin_dashboard'))
    job = Job(title=title, description=description, required_skills=skills,
              location=location, deadline=deadline, category_id=category_id, posted_by=current_user.id)
    db.session.add(job); db.session.commit()
    flash('Job posted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_job/<int:job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    if not current_user.is_admin: abort(403)
    job = Job.query.get_or_404(job_id)
    db.session.delete(job); db.session.commit()
    flash('Job deleted.', 'success'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit_job/<int:job_id>', methods=['POST'])
@login_required
def edit_job(job_id):
    if not current_user.is_admin: abort(403)
    job = Job.query.get_or_404(job_id)
    if request.form.get('title'): job.title = request.form.get('title').strip()
    job.deadline = request.form.get('deadline','').strip()
    db.session.commit(); flash('Job updated!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/applications/<int:job_id>')
@login_required
def admin_job_applications(job_id):
    if not current_user.is_admin: abort(403)
    job = Job.query.get_or_404(job_id)
    threshold = get_eligibility_threshold()
    
    # Sort by score descending (pure score ranking — what admin needs)
    all_apps = Application.query.filter_by(job_id=job_id).order_by(
        Application.match_score.desc(), Application.priority_tier.asc()).all()
    
    # Separate eligible vs not eligible
    eligible_apps = [a for a in all_apps if a.is_eligible]
    not_eligible_apps = [a for a in all_apps if not a.is_eligible]
    
    # Annotate ranks and skills
    for i, app in enumerate(eligible_apps):
        app.rank = i + 1
        app.is_top3 = i < 3
        try:
            app.skills_list = json.loads(app.matched_skills or '[]')
        except Exception:
            app.skills_list = []
    
    for i, app in enumerate(not_eligible_apps):
        app.rank = i + 1
        app.is_top3 = False
        try:
            app.skills_list = json.loads(app.matched_skills or '[]')
        except Exception:
            app.skills_list = []
    
    return render_template('admin_applications.html',
        job=job,
        eligible_apps=eligible_apps,
        not_eligible_apps=not_eligible_apps,
        total_apps=len(all_apps),
        threshold=threshold)

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin: abort(403)
    users = User.query.filter_by(is_admin=False).all()
    unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template('admin_users.html', users=users, unread_notifs=unread_notifs)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin: abort(403)
    user = db.session.get(User, user_id)
    if not user: abort(404)
    db.session.delete(user); db.session.commit()
    flash('User deleted.', 'success'); return redirect(url_for('admin_users'))

# ─── CV VIEW / DOWNLOAD ────────────────────────────────────────────────────────
@app.route('/admin/view_cv/<int:app_id>')
@login_required
def view_cv(app_id):
    if not current_user.is_admin: abort(403)
    application = Application.query.get_or_404(app_id)
    filename = application.cv_filename
    upload_folder = app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_folder, filename)
    if not os.path.exists(filepath): abort(404)
    ext = filename.rsplit('.',1)[-1].lower()
    mimetype = 'application/pdf' if ext == 'pdf' else f'image/{ext}'
    return send_from_directory(upload_folder, filename, mimetype=mimetype)

@app.route('/admin/download_cv/<int:app_id>')
@login_required
def download_cv(app_id):
    if not current_user.is_admin: abort(403)
    application = Application.query.get_or_404(app_id)
    return send_from_directory(app.config['UPLOAD_FOLDER'], application.cv_filename, as_attachment=True)

# ─── SEND MESSAGE TO USER ──────────────────────────────────────────────────────
@app.route('/admin/send_message/<int:app_id>', methods=['POST'])
@login_required
def send_message(app_id):
    if not current_user.is_admin: abort(403)
    application = Application.query.get_or_404(app_id)
    msg_type = request.form.get('msg_type', 'custom')
    custom_msg = request.form.get('message', '').strip()
    joining_date = request.form.get('joining_date', '').strip()
    user = application.applicant
    job = application.job

    if msg_type == 'hired':
        title = f"🎉 Congratulations! You've been selected for {job.title}"
        message = generate_hired_message(user.name, job.title, job.location, joining_date, application.match_score)
        notif_type = 'success'
    elif msg_type == 'rejected':
        title = f"Update on your application for {job.title}"
        message = generate_rejection_message(user.name, job.title, application.match_score,
                                             json.loads(application.matched_skills or '[]'),
                                             job.required_skills)
        notif_type = 'warning'
    else:
        title = f"Message regarding your {job.title} application"
        message = custom_msg
        notif_type = 'info'

    push_notification(user.id, title, message, notif_type)
    application.admin_message_sent = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Message sent!'})

def generate_hired_message(name, job_title, location, joining_date, score):
    jd = f"Your joining date is <strong>{joining_date}</strong>." if joining_date else "Joining details will be communicated separately."
    return f"""Dear <strong>{name}</strong>,<br><br>
We are thrilled to inform you that after a thorough review of your CV and qualifications, you have been <strong>selected</strong> for the position of <strong>{job_title}</strong> at our {location} office.<br><br>
Your CV achieved a match score of <strong>{score}%</strong>, demonstrating excellent alignment with our requirements.<br><br>
{jd}<br><br>
Please bring the following on your first day:<br>
• Original CNIC / Passport<br>
• 2 passport-size photographs<br>
• Educational certificates (originals)<br>
• Experience letters (if applicable)<br><br>
Congratulations once again! We look forward to having you as part of our team.<br><br>
<em>Best Regards,<br>HR Department — CV Guard Recruitment</em>"""

def generate_rejection_message(name, job_title, score, matched, required_skills_str):
    required = [s.strip() for s in required_skills_str.split(',')]
    missing = [s for s in required if s.lower() not in [m.lower() for m in matched]]
    miss_str = ', '.join(missing[:4]) if missing else 'N/A'
    tips = []
    if score < 30: tips.append("Work on aligning your CV more closely with job requirements")
    if missing: tips.append(f"Develop skills in: {miss_str}")
    tips.append("Consider adding measurable achievements to your CV")
    tips_html = ''.join([f'<li>{t}</li>' for t in tips])
    return f"""Dear <strong>{name}</strong>,<br><br>
Thank you for applying for the position of <strong>{job_title}</strong> and for the time you invested in submitting your application.<br><br>
After careful consideration, we regret to inform you that we will not be moving forward with your application at this time.<br><br>
<strong>Application Details:</strong><br>
• Match Score: <strong>{score}%</strong><br>
• Skills Matched: <strong>{', '.join(matched) if matched else 'None'}</strong><br>
• Missing Skills: <strong>{miss_str}</strong><br><br>
<strong>Suggestions to improve your profile:</strong><br>
<ul>{tips_html}</ul><br>
We encourage you to apply for future openings that match your profile. Your information will be kept on file.<br><br>
<em>Best Regards,<br>HR Department — CV Guard Recruitment</em>"""

# ─── SETTINGS ──────────────────────────────────────────────────────────────────
@app.route('/admin/settings', methods=['GET','POST'])
@login_required
def admin_settings():
    if not current_user.is_admin: abort(403)
    if request.method == 'POST':
        threshold = request.form.get('threshold','30').strip()
        try: threshold = str(max(0, min(100, float(threshold))))
        except: threshold = '30'
        set_setting('eligibility_threshold', threshold)
        # Re-evaluate all applications with new threshold
        threshold_f = float(threshold)
        for appl in Application.query.all():
            appl.is_eligible = appl.match_score >= threshold_f
        db.session.commit()
        # Theme
        theme = request.form.get('theme', 'dark')
        current_user.theme = theme
        db.session.commit()
        flash(f'Settings saved! Threshold: {threshold}%, Theme: {theme}', 'success')
        return redirect(url_for('admin_settings'))
    threshold = get_eligibility_threshold()
    categories = Category.query.all()
    unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template('admin_settings.html', threshold=threshold, categories=categories, unread_notifs=unread_notifs)

@app.route('/user/settings', methods=['GET','POST'])
@login_required
def user_settings():
    if request.method == 'POST':
        action = request.form.get('action', 'profile')

        if action == 'profile':
            name = request.form.get('name', current_user.name).strip()
            theme = request.form.get('theme', 'dark')
            if name:
                current_user.name = name
            current_user.theme = theme
            db.session.commit()
            flash('Profile updated successfully!', 'success')

        elif action == 'password':
            current_pw = request.form.get('current_password', '').strip()
            new_pw = request.form.get('new_password', '').strip()
            confirm_pw = request.form.get('confirm_password', '').strip()

            if not check_password_hash(current_user.password_hash, current_pw):
                flash('Current password is incorrect.', 'error')
            elif len(new_pw) < 6:
                flash('New password must be at least 6 characters.', 'error')
            elif new_pw != confirm_pw:
                flash('New passwords do not match.', 'error')
            else:
                current_user.password_hash = generate_password_hash(new_pw)
                db.session.commit()
                flash('Password changed successfully!', 'success')

        return redirect(url_for('user_settings'))

    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    notifs = enrich_notifs(Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(8).all())
    return render_template('user_settings.html', unread_notifs=unread, notifs=notifs)

# ─── CATEGORIES ────────────────────────────────────────────────────────────────
@app.route('/admin/add_category', methods=['POST'])
@login_required
def add_category():
    if not current_user.is_admin: abort(403)
    name = request.form.get('name','').strip()
    icon = request.form.get('icon','fa-briefcase').strip()
    color = request.form.get('color','purple').strip()
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name, icon=icon, color=color))
        db.session.commit()
        flash('Category added!', 'success')
    return redirect(url_for('admin_settings'))

@app.route('/admin/delete_category/<int:cat_id>', methods=['POST'])
@login_required
def delete_category(cat_id):
    if not current_user.is_admin: abort(403)
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat); db.session.commit()
    flash('Category deleted.', 'success')
    return redirect(url_for('admin_settings'))

# ─── NOTIFICATIONS ─────────────────────────────────────────────────────────────
@app.route('/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@app.route('/notifications/count')
@login_required
def notification_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    notifs = enrich_notifs(Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(8).all())
    return jsonify({'count': count, 'notifications': [
        {'id': n.id, 'title': n.title, 'message': n.message[:80],
         'type': n.notif_type, 'read': n.is_read, 'time': n.created_at.strftime('%d %b, %H:%M')}
        for n in notifs
    ]})

# ─── USER ──────────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def user_dashboard():
    if current_user.is_admin: return redirect(url_for('admin_dashboard'))
    cat_filter = request.args.get('cat', '')
    search = request.args.get('q', '')
    query = Job.query
    if cat_filter: query = query.filter_by(category_id=cat_filter)
    if search: query = query.filter(Job.title.ilike(f'%{search}%'))
    jobs = query.order_by(Job.created_at.desc()).all()
    categories = Category.query.all()
    my_apps = Application.query.filter_by(user_id=current_user.id).all()
    applied_job_ids = {a.job_id for a in my_apps}
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    notifs = enrich_notifs(Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(8).all())
    threshold = get_eligibility_threshold()
    return render_template('user_dashboard.html', jobs=jobs, categories=categories,
        applied_job_ids=applied_job_ids, my_apps=my_apps,
        unread_notifs=unread, notifs=notifs,
        cat_filter=cat_filter, search=search, threshold=threshold)

@app.route('/apply/<int:job_id>', methods=['POST'])
@login_required
def apply_job(job_id):
    job = Job.query.get_or_404(job_id)
    if Application.query.filter_by(user_id=current_user.id, job_id=job_id).first():
        return jsonify({'error': 'Already applied'}), 400
    if 'cv' not in request.files: return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['cv']
    if not file.filename: return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename): return jsonify({'error': 'Invalid file type. Use PDF, PNG, or JPG.'}), 400

    filename = secure_filename(f"cv_{current_user.id}_{job_id}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        cv_text = extract_text_from_file(filepath)
        if not cv_text or len(cv_text.strip()) < 20:
            os.remove(filepath)
            return jsonify({'error': 'Could not extract text. Ensure CV is not empty or corrupted.'}), 400

        score, matched_skills = match_cv_to_job(cv_text, job.description, job.required_skills)
        score = float(round(score, 1))
        tier = int(get_location_tier(current_user.city, job.location))
        threshold = get_eligibility_threshold()
        eligible = bool(score >= threshold)

        application = Application(user_id=current_user.id, job_id=job_id,
            cv_filename=filename, cv_text=cv_text, match_score=score,
            matched_skills=json.dumps(matched_skills), priority_tier=tier, is_eligible=eligible)
        db.session.add(application)

        # Notify ALL admins about new CV
        admins = User.query.filter_by(is_admin=True).all()
        for admin in admins:
            push_notification(admin.id,
                f"📄 New CV: {current_user.name} applied for {job.title}",
                f"{current_user.name} from {current_user.city or 'Unknown'} submitted their CV for '{job.title}'. Score: {score}% | Tier {tier} | {'Eligible ✓' if eligible else 'Not eligible ✗'}",
                'info')

        # Notify user of receipt
        push_notification(current_user.id,
            f"✅ Application submitted for {job.title}",
            f"Your CV has been received and analyzed. Match Score: {score}% | {'You meet the eligibility criteria!' if eligible else 'You did not meet the current eligibility threshold.'}",
            'success' if eligible else 'warning')

        db.session.commit()
        return jsonify({'success': True, 'score': score, 'eligible': eligible,
            'tier': tier, 'matched_skills': matched_skills, 'threshold': threshold,
            'status': 'Passed ✓' if eligible else 'Not Eligible ✗'})
    except Exception as e:
        if os.path.exists(filepath): os.remove(filepath)
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

@app.route('/my_applications')
@login_required
def my_applications():
    apps = Application.query.filter_by(user_id=current_user.id).order_by(Application.applied_at.desc()).all()
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    notifs = enrich_notifs(Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(8).all())
    return render_template('my_applications.html', applications=apps, unread_notifs=unread, notifs=notifs)

# ─── CHATBOTS ──────────────────────────────────────────────────────────────────
@app.route('/chatbot', methods=['POST'])
@login_required
def chatbot():
    message = request.json.get('message', '').lower().strip()
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    response = build_user_chatbot_response(message, jobs)
    return jsonify({'response': response})

@app.route('/admin/chatbot', methods=['POST'])
@login_required
def admin_chatbot():
    if not current_user.is_admin: return jsonify({'error': 'Unauthorized'}), 403
    message = request.json.get('message', '').lower().strip()
    jobs = Job.query.order_by(Job.created_at.desc()).all()
    applications = Application.query.all()
    users = User.query.filter_by(is_admin=False).all()
    response = build_admin_chatbot_response(message, jobs, applications, users)
    return jsonify({'response': response})

def build_user_chatbot_response(message, jobs):
    if any(w in message for w in ['hi','hello','hey','salam','assalam']):
        return f"Hello {current_user.name}! 👋 I'm your CV Guard AI Assistant.\n\nI can help you with:\n• Available vacancies & categories\n• Application deadlines\n• Your scores & status\n• How to apply\n• Location priority tiers\n\nWhat would you like to know?"
    if any(w in message for w in ['stats','statistic','overview','analytics']):
        my_apps = Application.query.filter_by(user_id=current_user.id).all()
        eligible = sum(1 for a in my_apps if a.is_eligible)
        avg = round(sum(a.match_score for a in my_apps)/len(my_apps),1) if my_apps else 0
        return f"📊 Your Stats:\n• Jobs available: {len(jobs)}\n• Your applications: {len(my_apps)}\n• Eligible: {eligible}\n• Average score: {avg}%"
    if any(w in message for w in ['vacancy','vacancies','jobs','job','available','opening','position']):
        if jobs:
            return f"📋 {len(jobs)} active vacancies:\n" + "\n".join([f"• {j.title} — {j.location}" + (f" (Deadline: {j.deadline})" if j.deadline else "") for j in jobs])
        return "No vacancies posted currently."
    if any(w in message for w in ['category','categories','field','department']):
        cats = Category.query.all()
        if cats:
            return "📂 Job Categories:\n" + "\n".join([f"• {c.name} ({len(c.jobs)} jobs)" for c in cats])
        return "No categories defined yet."
    if any(w in message for w in ['deadline','last date','due date','closing']):
        upcoming = [j for j in jobs if j.deadline]
        if upcoming:
            return "📅 Deadlines:\n" + "\n".join([f"• {j.title}: {j.deadline}" for j in upcoming])
        return "No deadlines set for current jobs."
    if any(w in message for w in ['my application','my apply','status','applied','my score']):
        my_apps = Application.query.filter_by(user_id=current_user.id).order_by(Application.match_score.desc()).all()
        if my_apps:
            return f"📁 Your {len(my_apps)} application(s):\n" + "\n".join([f"• {a.job.title}: {a.match_score}% — {'✅ Eligible' if a.is_eligible else '❌ Not Eligible'}" for a in my_apps[:5]])
        return "You haven't applied yet. Browse jobs and upload your CV!"
    if any(w in message for w in ['score','match','eligible','eligib','percent','calculate']):
        threshold = get_eligibility_threshold()
        return f"🤖 Scoring:\n• AI reads your CV (PDF/Image)\n• Compares with job requirements\n• TF-IDF semantic similarity + skill match\n• Current threshold: {threshold}% = Eligible ✓\n\nHigher score = better match!"
    if any(w in message for w in ['apply','how to','submit','upload','cv','resume']):
        return "📤 How to apply:\n1. Browse Job Board\n2. Click 'Apply Now'\n3. Upload CV (PDF/PNG/JPG)\n4. AI instantly scores your CV!\n\nTip: List your skills clearly for a higher score."
    if any(w in message for w in ['notification','message','update','news']):
        unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return f"🔔 You have {unread} unread notification(s).\nClick the bell icon to view messages from admin."
    if any(w in message for w in ['location','tier','priority','city','distance']):
        return "📍 Location Priority (Dynamic):\n🥇 Tier 1 = Same city as job\n🥈 Tier 2 = Nearby city\n🥉 Tier 3 = Distant city\n\nEach job prioritizes its own location first!\nYour city: " + (current_user.city or "Not set — update in Settings")
    if any(w in message for w in ['setting','profile','theme','dark','light']):
        return f"⚙️ Settings:\n• Go to Settings (top menu) to change:\n  - Dark/Light mode\n  - Your display name\n• Current theme: {current_user.theme}\n• Your city: {current_user.city or 'Not set'}"
    if any(w in message for w in ['how many','count','total','number of']):
        my_apps = Application.query.filter_by(user_id=current_user.id).count()
        return f"📊 Quick Count:\n• Total jobs: {len(jobs)}\n• Your applications: {my_apps}"
    if any(w in message for w in ['skill','requirement','qualification','required']):
        if jobs:
            return "🛠️ Required skills:\n" + "\n".join([f"• {j.title}: {j.required_skills}" for j in jobs[:5]])
        return "No jobs posted yet."
    if any(w in message for w in ['help','what can you','commands','menu']):
        return "🤖 CV Guard Assistant:\n\n• 'Show jobs' — all vacancies\n• 'My applications' — your status\n• 'How to apply' — guide\n• 'My score' — scoring info\n• 'Location tiers' — priority\n• 'Categories' — job fields\n• 'Deadlines' — closing dates\n• 'Notifications' — messages\n• 'Settings' — theme & profile"
    matched = [j for j in jobs if message in j.title.lower() or message in j.required_skills.lower()]
    if matched:
        return f"🔍 Found {len(matched)} job(s):\n" + "\n".join([f"• {j.title} ({j.location})" for j in matched[:3]])
    return f"I couldn't find info about '{message}'.\nTry: 'Show jobs', 'My applications', 'Help'"

def build_admin_chatbot_response(message, jobs, applications, users):
    import json as _json
    from collections import defaultdict
    if any(w in message for w in ['hi','hello','hey','salam']):
        return f"Hello Admin {current_user.name}! 👋 CV Guard AI at your service.\n\nI can:\n• Show best CVs per job\n• Give hiring recommendations\n• Analyze statistics\n• Show eligible/rejected candidates\n• Search by city or skill\n\nWhat do you need?"
    # Hiring recommendations (must be before 'best cv')
    if any(w in message for w in ['choose best','select best','who to hire','hire who','pick best','best for all','hiring recommendation','who should i hire','recommend candidate']):
        if not applications: return "No CVs submitted yet."
        job_best = defaultdict(list)
        for app in applications: job_best[app.job_id].append(app)
        lines = []
        for job in jobs:
            picks = sorted(job_best.get(job.id,[]), key=lambda a:(a.priority_tier,-a.match_score))
            ep = [p for p in picks if p.is_eligible]
            if ep:
                top = ep[0]
                try: skills = _json.loads(top.matched_skills or '[]')
                except: skills = []
                lines.append(f"✅ {job.title} → {top.applicant.name}\n   {top.applicant.city} | {top.match_score}% | Tier {top.priority_tier}\n   Matched: {', '.join(skills[:3])}")
            elif picks:
                lines.append(f"⚠️ {job.title} → {picks[0].applicant.name} ({picks[0].match_score}% — below threshold)")
            else:
                lines.append(f"❌ {job.title} → No applicants")
        return "🤖 AI Hiring Recommendations:\n\n" + "\n\n".join(lines) if lines else "No jobs posted."
    # Not eligible (before eligible)
    if any(w in message for w in ['not eligible','failed','rejected','low score']):
        fa = Application.query.filter_by(is_eligible=False).order_by(Application.match_score.desc()).limit(8).all()
        if fa: return "❌ Not Eligible:\n" + "\n".join([f"• {a.applicant.name} → {a.job.title}: {a.match_score}%" for a in fa])
        return "All applications are currently eligible!"
    # Best CVs
    if any(w in message for w in ['best cv','best cvs','top cv','top candidate','show best','show cvs']):
        if not applications: return "No CVs submitted yet."
        job_top = defaultdict(list)
        for app in applications: job_top[app.job_id].append(app)
        lines = []
        for job in jobs:
            apps = sorted(job_top.get(job.id,[]), key=lambda a:(a.priority_tier,-a.match_score))
            if apps:
                top = apps[0]
                try: skills = _json.loads(top.matched_skills or '[]')
                except: skills = []
                lines.append(f"🏆 {job.title}:\n   {top.applicant.name} ({top.applicant.city}) | {top.match_score}% | Tier {top.priority_tier}\n   Skills: {', '.join(skills) or 'None'}")
        return "📋 Best CV per job:\n\n" + "\n\n".join(lines) if lines else "No applications yet."
    # Eligible
    if any(w in message for w in ['eligible','passed','qualified','shortlist']):
        ea = Application.query.filter_by(is_eligible=True).order_by(Application.priority_tier.asc(), Application.match_score.desc()).limit(10).all()
        if ea: return f"✅ {len(ea)} Eligible Candidates:\n" + "\n".join([f"• {a.applicant.name} ({a.applicant.city}) → {a.job.title}: {a.match_score}% | Tier {a.priority_tier}" for a in ea])
        return "No eligible candidates yet."
    # Stats
    if any(w in message for w in ['stats','statistics','overview','summary','report','total','how many']):
        eligible_count = Application.query.filter_by(is_eligible=True).count()
        t1=Application.query.filter_by(priority_tier=1).count()
        t2=Application.query.filter_by(priority_tier=2).count()
        t3=Application.query.filter_by(priority_tier=3).count()
        avg = db.session.query(db.func.avg(Application.match_score)).scalar() or 0
        threshold = get_eligibility_threshold()
        return (f"📊 CV Guard Statistics:\n• Total Jobs: {len(jobs)}\n• Candidates: {len(users)}\n• Applications: {len(applications)}\n• Eligible: {eligible_count}\n• Avg Score: {avg:.1f}%\n• Threshold: {threshold}%\n\n📍 By Tier:\n• Tier 1 (Same city): {t1}\n• Tier 2 (Nearby): {t2}\n• Tier 3 (Other): {t3}")
    # Specific job candidates
    if any(w in message for w in ['for job','candidates for','cvs for','applicants for']):
        found = None
        for job in jobs:
            if job.title.lower() in message or any(w in message for w in job.title.lower().split()):
                found = job; break
        if found:
            apps = Application.query.filter_by(job_id=found.id).order_by(Application.priority_tier.asc(), Application.match_score.desc()).limit(5).all()
            if apps:
                lines = []
                for i,a in enumerate(apps,1):
                    try: skills = _json.loads(a.matched_skills or '[]')
                    except: skills = []
                    lines.append(f"{'🥇🥈🥉4️⃣5️⃣'[i-1]} {a.applicant.name} ({a.applicant.city})\n   {a.match_score}% | Tier {a.priority_tier} | {'✅' if a.is_eligible else '❌'}\n   Skills: {', '.join(skills) or 'None'}")
                return f"Candidates for '{found.title}':\n\n" + "\n\n".join(lines)
            return f"No applications for '{found.title}' yet."
        return "Please mention a specific job title. Say: 'candidates for Python Developer'"
    # All jobs
    if any(w in message for w in ['jobs','vacancies','opening','posted jobs','all jobs']):
        if jobs: return f"📋 {len(jobs)} Jobs:\n" + "\n".join([f"• {j.title} ({j.location}) | {len(j.applications)} applicants" for j in jobs])
        return "No jobs posted yet."
    # All users
    if any(w in message for w in ['users','candidates','applicants','registered','people']):
        if users: return f"👥 {len(users)} Candidates:\n" + "\n".join([f"• {u.name} ({u.city or 'N/A'}) | {len(u.applications)} app(s)" for u in users[:10]])
        return "No candidates yet."
    # Location
    if any(w in message for w in ['location','tier','city','priority','distance']):
        t1a = Application.query.filter_by(priority_tier=1,is_eligible=True).order_by(Application.match_score.desc()).limit(3).all()
        lines = [f"• {a.applicant.name} ({a.applicant.city}) — {a.job.title}: {a.match_score}%" for a in t1a]
        return "📍 Dynamic Tiers:\n🥇 Tier 1 = Same city as job\n🥈 Tier 2 = Nearby city\n🥉 Tier 3 = Distant city\n\nTop Tier 1 eligible:\n" + ("\n".join(lines) if lines else "None yet")
    # Help
    if any(w in message for w in ['help','what can you','commands','menu','options']):
        return "🤖 Admin AI Commands:\n\n• 'Show best CVs' — top CV per job\n• 'Hiring recommendations' — who to hire\n• 'Statistics' — full platform report\n• 'Eligible candidates' — shortlist\n• 'Not eligible' — failed apps\n• 'Candidates for [job]' — specific job\n• 'Show all jobs' — job list\n• 'Location analysis' — tier breakdown"
    # Smart search
    mj = [j for j in jobs if message in j.title.lower() or message in j.required_skills.lower()]
    if mj:
        job = mj[0]
        apps = Application.query.filter_by(job_id=job.id).order_by(Application.priority_tier.asc(), Application.match_score.desc()).limit(3).all()
        if apps:
            return f"'{job.title}' top candidates:\n" + "\n".join([f"• {a.applicant.name} ({a.applicant.city}): {a.match_score}% | {'✅' if a.is_eligible else '❌'}" for a in apps])
        return f"Job '{job.title}' exists but has no applications yet."
    return f"I couldn't find info about '{message}'.\nTry: 'Best CVs', 'Statistics', 'Hiring recommendations', 'Help'"

@app.route('/admin/get_top_n/<int:job_id>/<int:n>')
@login_required
def get_top_n_candidates(job_id, n):
    """API: Return top N eligible candidates for a job, sorted by score."""
    if not current_user.is_admin: abort(403)
    job = Job.query.get_or_404(job_id)
    threshold = get_eligibility_threshold()
    
    eligible = Application.query.filter_by(job_id=job_id, is_eligible=True)\
        .order_by(Application.match_score.desc(), Application.priority_tier.asc()).all()
    
    total_eligible = len(eligible)
    requested = min(n, total_eligible)
    top_n = eligible[:requested]
    
    result = []
    for i, app in enumerate(top_n):
        try: skills = json.loads(app.matched_skills or '[]')
        except: skills = []
        result.append({
            'rank': i + 1,
            'id': app.id,
            'name': app.applicant.name,
            'email': app.applicant.email,
            'city': app.applicant.city or 'N/A',
            'score': app.match_score,
            'tier': app.priority_tier,
            'skills': skills,
        })
    
    return jsonify({
        'success': True,
        'requested': n,
        'total_eligible': total_eligible,
        'returned': requested,
        'short': n > total_eligible,
        'short_msg': f'Only {total_eligible} eligible candidate(s) available — showing all.' if n > total_eligible else None,
        'candidates': result
    })

# ─── TOP CV SELECTION ──────────────────────────────────────────────────────────

@app.route('/admin/select_top_cvs/<int:job_id>', methods=['POST'])
@login_required
def select_top_cvs(job_id):
    """Admin manually marks top 1/2/3 CVs as shortlisted and notifies candidates."""
    if not current_user.is_admin:
        abort(403)
    job = Job.query.get_or_404(job_id)
    selected_ids = request.json.get('selected_ids', [])  # list of app IDs
    
    if not selected_ids:
        return jsonify({'error': 'No candidates selected'}), 400
    if len(selected_ids) > 3:
        return jsonify({'error': 'Maximum 3 candidates can be shortlisted'}), 400

    results = []
    for app_id in selected_ids:
        appl = Application.query.get(app_id)
        if appl and appl.job_id == job_id:
            # Notify selected candidate
            push_notification(
                appl.user_id,
                f"🌟 You've been shortlisted for {job.title}!",
                generate_shortlist_message(appl.applicant.name, job.title, job.location, appl.match_score),
                'success'
            )
            appl.admin_message_sent = True
            results.append(appl.applicant.name)
    
    db.session.commit()
    return jsonify({'success': True, 'notified': results})

def generate_shortlist_message(name, job_title, location, score):
    return f"""Dear <strong>{name}</strong>,<br><br>
🌟 Congratulations! After reviewing all applications for <strong>{job_title}</strong>, you have been <strong>shortlisted</strong> as one of our top candidates.<br><br>
Your CV achieved a match score of <strong>{score}%</strong>, placing you among the best applicants for this role at our <strong>{location}</strong> office.<br><br>
<strong>Next Steps:</strong><br>
• Our HR team will contact you within 3–5 business days<br>
• Prepare your original documents for verification<br>
• You may be called for a formal interview<br><br>
Please ensure your contact information is up to date.<br><br>
<em>Best Regards,<br>HR Department — CV Guard Recruitment</em>"""

# ─── ADMIN PASSWORD RESET ──────────────────────────────────────────────────────

@app.route('/admin/change_password', methods=['POST'])
@login_required
def admin_change_password():
    if not current_user.is_admin:
        abort(403)
    current_pw = request.form.get('current_password', '').strip()
    new_pw = request.form.get('new_password', '').strip()
    confirm_pw = request.form.get('confirm_password', '').strip()

    if not check_password_hash(current_user.password_hash, current_pw):
        flash('Current password is incorrect.', 'error')
    elif len(new_pw) < 6:
        flash('New password must be at least 6 characters.', 'error')
    elif new_pw != confirm_pw:
        flash('New passwords do not match.', 'error')
    else:
        current_user.password_hash = generate_password_hash(new_pw)
        db.session.commit()
        flash('Password changed successfully!', 'success')
    return redirect(url_for('admin_settings'))

# Also allow admin to reset ANY user's password
@app.route('/admin/reset_user_password/<int:user_id>', methods=['POST'])
@login_required
def reset_user_password(user_id):
    if not current_user.is_admin:
        abort(403)
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    new_pw = request.json.get('new_password', 'Reset@123').strip()
    user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    # Notify user
    push_notification(user.id,
        'Password Reset by Admin',
        f'Your password has been reset. New temporary password: <strong>{new_pw}</strong><br>Please login and change it immediately from Settings.',
        'warning')
    return jsonify({'success': True, 'message': f'Password reset for {user.name}'})

# ─── NETWORK INFO ──────────────────────────────────────────────────────────────

@app.route('/network_info')
def network_info():
    """Returns the server's network IP for multi-device access."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'
    return jsonify({
        'local_ip': local_ip,
        'port': 5000,
        'url': f'http://{local_ip}:5000',
        'instructions': {
            'step1': 'Make sure all devices are on the SAME WiFi network',
            'step2': f'Open this URL on any device: http://{local_ip}:5000',
            'step3': 'Admin: admin@cvguard.com / admin123',
            'step4': 'Users can register and upload CVs from their phones/laptops'
        }
    })

# ─── INIT ──────────────────────────────────────────────────────────────────────
def create_tables():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@cvguard.com').first():
            admin = User(name='Admin', email='admin@cvguard.com',
                        password_hash=generate_password_hash('admin123'),
                        city='Rawalpindi', is_admin=True)
            db.session.add(admin)
        if not Setting.query.filter_by(key='eligibility_threshold').first():
            db.session.add(Setting(key='eligibility_threshold', value='30'))
        # Seed categories
        default_cats = [
            ('Technology & IT', 'fa-laptop-code', 'blue'),
            ('Engineering', 'fa-gears', 'orange'),
            ('Finance & Banking', 'fa-coins', 'green'),
            ('Healthcare & Medical', 'fa-stethoscope', 'red'),
            ('Education & Teaching', 'fa-graduation-cap', 'purple'),
            ('Marketing & Sales', 'fa-bullhorn', 'pink'),
            ('Design & Creative', 'fa-palette', 'violet'),
            ('HR & Administration', 'fa-users', 'gray'),
            ('Legal', 'fa-scale-balanced', 'yellow'),
            ('Customer Service', 'fa-headset', 'cyan'),
        ]
        for name, icon, color in default_cats:
            if not Category.query.filter_by(name=name).first():
                db.session.add(Category(name=name, icon=icon, color=color))
        db.session.flush()
        # Demo jobs
        if Job.query.count() == 0:
            admin_user = User.query.filter_by(is_admin=True).first()
            tech_cat = Category.query.filter_by(name='Technology & IT').first()
            eng_cat = Category.query.filter_by(name='Engineering').first()
            des_cat = Category.query.filter_by(name='Design & Creative').first()
            demo_jobs = [
                Job(title='Python Developer', description='Build Flask REST APIs and backend systems with SQL databases and ORM frameworks.',
                    required_skills='Python, Flask, SQL, REST API, SQLAlchemy, Git',
                    location='Rawalpindi', deadline='2025-03-31', category_id=tech_cat.id if tech_cat else None, posted_by=admin_user.id),
                Job(title='UI/UX Designer', description='Design beautiful interfaces using Figma and modern CSS frameworks for web and mobile apps.',
                    required_skills='Figma, CSS, HTML, Tailwind, Adobe XD, Prototyping',
                    location='Lahore', deadline='2025-04-15', category_id=des_cat.id if des_cat else None, posted_by=admin_user.id),
                Job(title='Civil Engineer', description='Design and supervise construction projects including roads, bridges, and buildings.',
                    required_skills='AutoCAD, Structural Analysis, Project Management, Site Supervision, Civil Design',
                    location='Karachi', deadline='2025-04-30', category_id=eng_cat.id if eng_cat else None, posted_by=admin_user.id),
            ]
            for j in demo_jobs: db.session.add(j)
        db.session.commit()

if __name__ == '__main__':
    import socket
    os.makedirs(os.path.join(os.path.dirname(__file__), 'static', 'uploads'), exist_ok=True)
    create_tables()
    # Get local IP for display
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'
    print("\n" + "="*55)
    print("  CV Guard — Started Successfully!")
    print("="*55)
    print(f"  Local:    http://127.0.0.1:5000")
    print(f"  Network:  http://{local_ip}:5000")
    print(f"  Admin:    admin@cvguard.com / admin123")
    print("="*55)
    print("  Share the Network URL with mobile/laptop users")
    print("  (All devices must be on same WiFi network)")
    print("="*55 + "\n")
    # 0.0.0.0 means accessible from ALL devices on the network
    app.run(debug=False, host='0.0.0.0', port=5000)
