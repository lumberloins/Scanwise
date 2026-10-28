"""
ScanWise Web Views Blueprint.
Renders the main technician diagnostic dashboard.
"""
import os
import json
from flask import Blueprint, render_template, current_app

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def dashboard():
    profiles_path = os.path.join(current_app.root_path, 'profiles', 'emr_profiles.json')
    try:
        with open(profiles_path, 'r') as f:
            profiles = json.load(f)
    except Exception:
        profiles = {}

    return render_template('dashboard.html', profiles=profiles)
