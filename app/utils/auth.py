from functools import wraps
from flask import session, redirect, url_for, flash, request
from app.models.models import User

def login_required(f):
    """Decorator to require user authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """Decorator to require specific user roles"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            
            from app.models.user import User
            user = User.get_by_id(session['user_id'])
            if not user or user['role'] not in allowed_roles:
                flash('Access denied. {} only.'.format(' / '.join(allowed_roles)), 'error')
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_current_user():
    """Get the current logged-in user"""
    if 'user_id' in session:
        from app.models.user import User
        return User.get_by_id(session['user_id'])
    return None

def is_authenticated():
    """Check if user is authenticated"""
    return 'user_id' in session

def login_user(user):
    """Log in a user"""
    session['user_id'] = user.id
    session['user_role'] = user.role
    session['username'] = user.username
    session.permanent = True

def logout_user():
    """Log out the current user"""
    session.clear()

def get_redirect_url_for_role(role):
    """Get the appropriate dashboard URL based on user role"""
    redirect_urls = {
        'customer': 'customer.dashboard',
        'seller': 'seller.dashboard', 
        'admin': 'admin.dashboard',
        'rider': 'rider.dashboard'
    }
    return redirect_urls.get(role, 'main.index')