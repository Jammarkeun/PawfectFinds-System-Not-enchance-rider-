from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.models import User, SellerApplication
from app.models.otp import OTP
from app.services.email_service import EmailService
from app.utils.auth import login_user, logout_user, get_redirect_url_for_role, login_required
from datetime import datetime, timedelta
import re

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me', False)
        
        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if user.status == 'inactive':
                flash('Your account is inactive. Please contact support.', 'error')
                return render_template('auth/login.html')
            elif user.status == 'suspended':
                flash('Your account has been suspended. Please contact support.', 'error')
                return render_template('auth/login.html')
            
            login_user(user, remember=remember_me)
            
            # Redirect based on role
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            redirect_route = get_redirect_url_for_role(user.role)
            return redirect(url_for(redirect_route))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        zip_code = request.form.get('zip_code', '').strip()
        
        # Validation
        errors = []
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters long.')
        
        if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            errors.append('Please enter a valid email address.')
        
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters long.')
        
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        if not first_name or not last_name:
            errors.append('First name and last name are required.')
        
        # Check if username or email already exists
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            if existing_user.username == username:
                errors.append('Username already exists.')
            if existing_user.email == email:
                errors.append('Email already exists.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Store form data in session for OTP verification
        session['registration_data'] = {
            'username': username,
            'email': email,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'address': address,
            'city': city,
            'state': state,
            'zip_code': zip_code
        }
        
        # Generate and send OTP
        otp_service = OTP()
        otp_code = otp_service.generate_otp(email)
        
        if not otp_code:
            flash('Failed to generate OTP. Please try again.', 'error')
            return render_template('auth/register.html')
        
        # Send OTP via email
        email_service = EmailService()
        email_sent = email_service.send_otp_email(email, otp_code)
        
        if not email_sent:
            flash('Failed to send verification email. Please try again.', 'error')
            return render_template('auth/register.html')
        
        # Redirect to OTP verification page
        return redirect(url_for('auth.verify_otp', email=email))
    
    return render_template('auth/register.html')

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = request.args.get('email')
    if not email:
        flash('Invalid verification request.', 'error')
        return redirect(url_for('auth.register'))
    
    if request.method == 'POST':
        otp_code = request.form.get('otp', '').strip()
        
        if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
            flash('Please enter a valid 6-digit OTP.', 'error')
            return render_template('auth/otp_verification_new.html', email=email)
        
        # Verify OTP
        otp_service = OTP()
        if not otp_service.verify_otp(email, otp_code):
            flash('Invalid or expired OTP. Please try again.', 'error')
            return render_template('auth/otp_verification_new.html', email=email)
        
        # Get registration data from session
        reg_data = session.get('registration_data')
        if not reg_data:
            flash('Session expired. Please register again.', 'error')
            return redirect(url_for('auth.register'))
        
        # Create new user
        new_user = User(
            username=reg_data['username'],
            email=reg_data['email'],
            first_name=reg_data['first_name'],
            last_name=reg_data['last_name'],
            phone=reg_data['phone'],
            address=reg_data['address'],
            city=reg_data['city'],
            state=reg_data['state'],
            zip_code=reg_data['zip_code'],
            role='customer',
            status='active',
            email_verified=True,
            email_verified_at=datetime.utcnow()
        )
        new_user.set_password(reg_data['password'])
        
        try:
            db.session.add(new_user)
            db.session.commit()
            
            # Clean up session
            if 'registration_data' in session:
                session.pop('registration_data')
            
            # Log the user in
            login_user(new_user)
            
            flash('Registration successful! Welcome to Pawfect Finds!', 'success')
            return redirect(url_for('public.home'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'User registration failed: {str(e)}')
            flash('Registration failed. Please try again.', 'error')
            return redirect(url_for('auth.register'))
    
    return render_template('auth/otp_verification_new.html', email=email)

@auth_bp.route('/resend-otp', methods=['POST'])
def resend_otp():
    email = request.form.get('email')
    if not email:
        return jsonify({'success': False, 'message': 'Email is required'}), 400
    
    # Generate new OTP
    otp_service = OTP()
    otp_code = otp_service.generate_otp(email)
    
    if not otp_code:
        return jsonify({'success': False, 'message': 'Failed to generate OTP'}), 500
    
    # Send OTP via email
    email_service = EmailService()
    email_sent = email_service.send_otp_email(email, otp_code)
    
    if not email_sent:
        return jsonify({'success': False, 'message': 'Failed to send OTP'}), 500
    
    return jsonify({'success': True, 'message': 'OTP resent successfully'})

@auth_bp.route('/become-seller', methods=['GET', 'POST'])
@login_required
def become_seller():
    from app.utils.auth import get_current_user
    user = get_current_user()
    
    # Check if user is already a seller
    if user.role == 'seller':
        flash('You are already a seller.', 'info')
        return redirect(url_for('seller.dashboard'))
    
    # Check if user already has a pending application
    existing_application = SellerApplication.query.filter_by(
        user_id=user.id, 
        status='pending'
    ).first()
    
    if existing_application:
        flash('You already have a pending seller application.', 'info')
        return render_template('auth/become_seller.html', application=existing_application)
    
    if request.method == 'POST':
        business_name = request.form.get('business_name', '').strip()
        business_description = request.form.get('business_description', '').strip()
        business_address = request.form.get('business_address', '').strip()
        tax_id = request.form.get('tax_id', '').strip()
        business_phone = request.form.get('business_phone', '').strip()
        business_email = request.form.get('business_email', '').strip().lower()
        
        # Validation
        errors = []
        
        if not business_name:
            errors.append('Business name is required.')
        
        if not business_address:
            errors.append('Business address is required.')
        
        if not business_phone:
            errors.append('Business phone is required.')
        
        if not business_email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', business_email):
            errors.append('Please enter a valid business email address.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/become_seller.html')
        
        # Create seller application
        application = SellerApplication(
            user_id=user.id,
            business_name=business_name,
            business_description=business_description,
            business_address=business_address,
            tax_id=tax_id,
            phone=business_phone,
            email=business_email,
            status='pending'
        )
        
        try:
            db.session.add(application)
            db.session.commit()
            
            flash('Your seller application has been submitted successfully! We will review it and notify you soon.', 'success')
            return redirect(url_for('customer.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to submit application. Please try again.', 'error')
    
    return render_template('auth/become_seller.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Please enter your email address.', 'error')
            return render_template('auth/forgot_password.html')
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # In a real application, you would send a password reset email here
            # For now, we'll just show a success message
            flash('If an account with that email exists, you will receive password reset instructions.', 'info')
        else:
            flash('If an account with that email exists, you will receive password reset instructions.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    from app.utils.auth import get_current_user
    user = get_current_user()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not current_password:
            flash('Current password is required.', 'error')
            return render_template('auth/change_password.html')
        
        if not user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('auth/change_password.html')
        
        if not new_password or len(new_password) < 6:
            flash('New password must be at least 6 characters long.', 'error')
            return render_template('auth/change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('auth/change_password.html')
        
        # Update password
        user.set_password(new_password)
        
        try:
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('customer.dashboard') if user.role == 'customer' else url_for(f'{user.role}.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to change password. Please try again.', 'error')
    
    return render_template('auth/change_password.html')