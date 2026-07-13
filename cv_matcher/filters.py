"""
Custom Jinja2 filters for the CV Guard app
"""
import json, re
from markupsafe import Markup


def _html_to_plain(html: str) -> str:
    """Convert HTML to fully clean plain text — no tags, no entities."""
    t = str(html)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</p>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<li\s*/?>', '• ', t, flags=re.IGNORECASE)
    t = re.sub(r'</li>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<ul[^>]*>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'</ul>', '\n', t, flags=re.IGNORECASE)
    for tag in ['strong', 'b', 'em', 'i', 'u', 'span', 'div', 'p', 'h1', 'h2', 'h3']:
        t = re.sub(rf'<{tag}[^>]*>(.*?)</{tag}>', r'\1',
                   t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r'<[^>]+>', '', t)
    for ent, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                      ('&quot;', '"'), ('&#39;', "'"), ('&#34;', '"'),
                      ('&#x27;', "'"), ('&nbsp;', ' ')]:
        t = t.replace(ent, char)
    lines = [l.strip() for l in t.split('\n')]
    lines = [l for l in lines if l]
    return '\n'.join(lines)


def register_filters(app):

    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return json.loads(value or '[]')
        except Exception:
            return []

    @app.template_filter('clean_text')
    def clean_text_filter(value):
        """Strip all HTML — returns clean plain text. Use instead of striptags."""
        return _html_to_plain(str(value))

    @app.template_filter('tojson_safe')
    def tojson_safe_filter(notifications):
        """Serialize notifications to safe JSON for <script> tags.
        plain_text = fully clean readable text, zero HTML."""
        result = []
        for n in notifications:
            full_plain = _html_to_plain(n.message)
            result.append({
                'id':         n.id,
                'title':      n.title,
                'plain_text': full_plain,
                'notif_type': n.notif_type,
                'is_read':    n.is_read,
                'created_at': n.created_at.strftime('%d %b %Y at %H:%M'),
            })
        serialized = json.dumps(result, ensure_ascii=False)
        serialized = serialized.replace('</', '<\\/')   # prevent </script> injection
        return Markup(serialized)
