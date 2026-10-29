"""
ScanWise Web Views Blueprint.
Tech Mode (/) for onsite technicians, Engineering Mode (/engineering) for deep analysis.
"""
import json
import os

from flask import Blueprint, current_app, render_template

views_bp = Blueprint('views', __name__)


def _profiles():
    profiles_path = os.path.join(current_app.root_path, 'profiles', 'emr_profiles.json')
    try:
        with open(profiles_path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


@views_bp.route('/')
def tech():
    return render_template('tech.html', profiles=_profiles(), mode='tech')


@views_bp.route('/engineering')
def engineering():
    return render_template('engineering.html', profiles=_profiles(), mode='engineering')
