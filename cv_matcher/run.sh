#!/bin/bash
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        CV Guard — AI Recruitment Platform v3.0       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "📦 Installing dependencies..."
pip install flask flask-sqlalchemy flask-login werkzeug scikit-learn pdfplumber pillow pytesseract numpy markupsafe --break-system-packages -q
echo "🔍 Installing Tesseract OCR..."
sudo apt-get install -y tesseract-ocr -q 2>/dev/null || brew install tesseract 2>/dev/null || echo "Install Tesseract manually for image CVs"
mkdir -p static/uploads
echo ""
echo "🚀 Starting CV Guard..."
echo ""
python app.py
