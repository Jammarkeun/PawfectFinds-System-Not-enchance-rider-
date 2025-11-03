from functools import wraps
from flask import session, redirect, url_for, flash, request, abort, jsonify, g
from app.models.user import User
import time
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import hmac

# Rate limiting storage (in production, use Redis or similar)
rate_limit_storage = defaultdict(list)

# CSRF token management
def generate_csrf_token():
    """Generate CSRF token for the current session"""
    if 'csrf_token' not in session:
        session['csrf_token'] = hashlib.sha256(str(time.time()).encode()).hexdigest()[:32]
    return session['csrf_token']

def validate_csrf_token(token):
    """Validate CSRF token"""
    return token and session.get('csrf_token') == token

def rate_limit(max_requests=60, window=60):
    """Rate limiting decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get client identifier (IP + User ID if logged in)
            client_id = request.remote_addr
            if 'user_id' in session:
                client_id += f"_user_{session['user_id']}"
            
            now = time.time()
            # Clean old entries
            rate_limit_storage[client_id] = [
                timestamp for timestamp in rate_limit_storage[client_id]
                if now - timestamp < window
            ]
            
            # Check rate limit
            if len(rate_limit_storage[client_id]) >= max_requests:
                if request.is_json:
                    return jsonify({'error': 'Rate limit exceeded'}), 429
                flash('Too many requests. Please try again later.', 'error')
                return abort(429)
            
            # Add current request
            rate_limit_storage[client_id].append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def validate_session():
    """Validate session integrity"""
    if 'user_id' not in session:
        return False
    
    # Check session timeout (optional)
    if 'login_time' in session:
        session_duration = time.time() - session['login_time']
        if session_duration > 86400:  # 24 hours
            session.clear()
            return False
    
    # Validate user still exists and is active
    user = User.get_by_id(session['user_id'])
    if not user or user['status'] != 'active':
        session.clear()
        return False
    
    return True

def login_required(f):
    """Enhanced decorator to require user authentication with session validation"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not validate_session():
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def csrf_protected(f):
    """CSRF protection decorator for state-changing operations"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')
            if not validate_csrf_token(token):
                if request.is_json:
                    return jsonify({'error': 'CSRF token validation failed'}), 403
                flash('Security token validation failed. Please try again.', 'error')
                return redirect(request.referrer or url_for('public.landing'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_role):
    """Decorator to require specific user role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            
            user = User.get_by_id(session['user_id'])
            if not user or user['role'] != required_role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('public.landing'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator specifically for admin access"""
    return role_required('admin')(f)

def seller_required(f):
    """Decorator specifically for seller access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        
        user = User.get_by_id(session['user_id'])
        if not user or user['role'] != 'seller':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('public.landing'))
        
        # Make sure the user object is available in templates
        from flask import g
        g.current_user = user
        
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    """Decorator specifically for regular user access"""
    return role_required('user')(f)

def anonymous_required(f):
    """Decorator to require user NOT to be logged in (for login/signup pages)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            user = User.get_by_id(session['user_id'])
            if user:
                if user['role'] == 'admin':
                    return redirect(url_for('admin.dashboard'))
                elif user['role'] == 'seller':
                    return redirect(url_for('seller.dashboard'))
                else:
                    return redirect(url_for('user.dashboard'))
        return f(*args, **kwargs)
    return decorated_function
