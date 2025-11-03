from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app.models.user import User
from app.utils.decorators import anonymous_required, login_required
from app.forms import LoginForm, SignupForm, OTPVerificationForm, PasswordResetRequestForm, PasswordResetForm, ChangePasswordForm
from app.services.email_service import EmailService
import secrets
import hashlib
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@anonymous_required
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip()
        password = form.password.data
        
        user = User.authenticate(email, password)
        if user:
            if user['status'] != 'active':
                flash('Your account has been deactivated. Please contact support.', 'error')
                return render_template('auth/login.html', form=form)
            
            session['user_id'] = user['id']
            session['user_role'] = user['role']
            session.permanent = True
            
            # Redirect based on role
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user['role'] == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user['role'] == 'seller':
                return redirect(url_for('seller.dashboard'))
            elif user['role'] == 'rider':
                # Mark rider as available when they log in
                from app.services.database import Database
                from datetime import datetime
                
                db = Database()
                
                # Check if rider exists in availability table
                rider_check = db.execute_query(
                    "SELECT id FROM rider_availability WHERE rider_id = %s",
                    (user['id'],),
                    fetch=True
                )
                
                if rider_check:
                    # Update existing rider
                    db.execute_query(
                        """
                        UPDATE rider_availability 
                        SET is_online = 1, 
                            is_available = 1, 
                            last_online = %s 
                        WHERE rider_id = %s
                        """,
                        (datetime.utcnow(), user['id'])
                    )
                else:
                    # Insert new rider
                    db.execute_query(
                        """
                        INSERT INTO rider_availability 
                        (rider_id, is_online, is_available, last_online)
                        VALUES (%s, 1, 1, %s)
                        """,
                        (user['id'], datetime.utcnow())
                    )
                
                return redirect(url_for('rider.dashboard'))
            else:
                return redirect(url_for('public.browse_products'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/signup', methods=['GET', 'POST'])
@anonymous_required
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        email = form.email.data.strip()
        password = form.password.data
        first_name = form.first_name.data.strip()
        last_name = form.last_name.data.strip()
        phone = form.phone.data.strip()
        address = form.address.data.strip()
        country = form.country.data
        city = form.city.data.strip()
        id_picture = form.id_picture.data

        # Check if user exists
        if User.get_by_email(email):
            flash('An account with this email already exists.', 'error')
            return render_template('auth/signup_multi_step.html', form=form)

        # Generate OTP and store in session
        import random
        otp_code = str(random.randint(100000, 999999))
        session['signup_data'] = {
            'email': email,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'address': address,
            'country': country,
            'city': city,
            'otp_code': otp_code
        }

        # Handle file upload for ID picture
        id_picture_filename = None
        if id_picture and hasattr(id_picture, 'filename') and id_picture.filename:
            import os
            from werkzeug.utils import secure_filename
            from PIL import Image
            import uuid

            # Create uploads directory if it doesn't exist
            uploads_dir = os.path.join('static', 'uploads', 'id_pictures')
            os.makedirs(uploads_dir, exist_ok=True)

            # Generate unique filename
            file_ext = os.path.splitext(id_picture.filename)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.pdf']:
                file_ext = '.jpg'  # Default to jpg if unknown extension
            unique_filename = f"{uuid.uuid4().hex}_{email.replace('@', '_')}{file_ext}"
            id_picture_path = os.path.join(uploads_dir, unique_filename)

            try:
                # Open and process the image
                image = Image.open(id_picture)

                # Convert to RGB if necessary (for PNG with transparency)
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')

                # Resize to a reasonable size (max 800x800, maintain aspect ratio)
                max_size = (800, 800)
                image.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save as JPEG with good quality
                image.save(id_picture_path, 'JPEG', quality=85, optimize=True)
                id_picture_filename = f"uploads/id_pictures/{unique_filename}"

                # Also create a profile image version (smaller size)
                profile_image = image.copy()
                profile_max_size = (400, 400)
                profile_image.thumbnail(profile_max_size, Image.Resampling.LANCZOS)

                # Create profile image directory if it doesn't exist
                profile_dir = os.path.join('static', 'uploads', 'profiles')
                os.makedirs(profile_dir, exist_ok=True)

                # Generate profile image filename
                profile_filename = f"{uuid.uuid4().hex}_{email.replace('@', '_')}_profile.jpg"
                profile_path = os.path.join(profile_dir, profile_filename)
                profile_image.save(profile_path, 'JPEG', quality=85, optimize=True)
                profile_image_filename = f"uploads/profiles/{profile_filename}"

            except Exception as e:
                # Fallback to original upload if processing fails
                filename = secure_filename(id_picture.filename)
                if filename:
                    fallback_filename = f"{uuid.uuid4().hex}_{filename}"
                    fallback_path = os.path.join(uploads_dir, fallback_filename)
                    id_picture.save(fallback_path)
                    id_picture_filename = f"uploads/id_pictures/{fallback_filename}"

        # Store file info in session
        session['signup_data']['id_picture'] = id_picture_filename
        if 'profile_image_filename' in locals():
            session['signup_data']['profile_image'] = profile_image_filename

        # Send OTP email via Email Service
        sent = EmailService.send_otp_email(email, otp_code)
        if not sent:
            flash('We could not send the verification code. Please try again later.', 'error')
            return render_template('auth/signup_multi_step.html', form=form)
        
        # Redirect to OTP verification
        return redirect(url_for('auth.verify_otp', email=email))
    elif request.method == 'POST':
        flash('Please correct the errors in the form.', 'error')

    return render_template('auth/signup_multi_step.html', form=form)

@auth_bp.route('/verify-otp/<email>', methods=['GET', 'POST'])
@anonymous_required
def verify_otp(email):
    form = OTPVerificationForm()
    
    if form.validate_on_submit():
        otp_code = form.otp_code.data
        
        # Debug logging
        current_app.logger.info(f"OTP verification attempt for {email}")
        current_app.logger.info(f"Entered OTP: {otp_code}")
        current_app.logger.info(f"Session signup_data exists: {'signup_data' in session}")
        if 'signup_data' in session:
            current_app.logger.info(f"Stored OTP: {session['signup_data'].get('otp_code')}")
            current_app.logger.info(f"Email match: {session['signup_data'].get('email') == email}")
        
        # Check if OTP matches
        if 'signup_data' in session and session['signup_data'].get('otp_code') == otp_code:
            # Create user account
            signup_data = session['signup_data']
            
            try:
                # Generate username from email
                username = signup_data['email'].split('@')[0]
                
                # Ensure username is unique
                counter = 1
                original_username = username
                while User.get_by_username(username):
                    username = f"{original_username}{counter}"
                    counter += 1
                
                user = User.create(
                    username=username,
                    email=signup_data['email'],
                    password=signup_data['password'],
                    first_name=signup_data['first_name'],
                    last_name=signup_data['last_name'],
                    phone=signup_data['phone'],
                    address=signup_data['address'],
                    country=signup_data['country'],
                    city=signup_data['city'],
                    id_picture=signup_data.get('id_picture'),
                    profile_image=signup_data.get('profile_image')
                )

                if user:
                    # Clear signup data from session
                    session.pop('signup_data', None)
                    flash('Account created successfully! Please login.', 'success')
                    return redirect(url_for('auth.login'))
                else:
                    flash('Failed to create account. Please try again.', 'error')
            except Exception as e:
                flash('An error occurred while creating your account.', 'error')
        else:
            flash('Invalid OTP code. Please try again.', 'error')
    
    return render_template('auth/otp_verification.html', form=form, email=email)

@auth_bp.route('/resend-otp', methods=['POST'])
@anonymous_required
def resend_otp():
    if 'signup_data' in session:
        import random
        otp_code = str(random.randint(100000, 999999))
        session['signup_data']['otp_code'] = otp_code
        
        # Send OTP email via Email Service
        email = session['signup_data']['email']
        if EmailService.send_otp_email(email, otp_code):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to send email'})
    
    return jsonify({'success': False, 'error': 'No signup data found'})

@auth_bp.route('/test-otp', methods=['GET', 'POST'])
def test_otp():
    """Test route for OTP functionality - for development only"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'})
        
        import random
        otp_code = str(random.randint(100000, 999999))
        
        # Test email sending via Email Service
        success = EmailService.send_otp_email(email, otp_code)
        
        return jsonify({
            'success': success,
            'otp_code': otp_code,
            'message': 'OTP sent successfully' if success else 'Failed to send OTP'
        })
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>OTP Test</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input[type="email"] { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .result { margin-top: 20px; padding: 10px; border-radius: 4px; }
            .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <h2>🔧 OTP Test Page</h2>
        <p>This page helps you test the OTP email functionality.</p>
        
        <form id="otpForm">
            <div class="form-group">
                <label for="email">Test Email Address:</label>
                <input type="email" id="email" name="email" required placeholder="your@email.com">
            </div>
            <button type="submit">Send Test OTP</button>
        </form>
        
        <div id="result"></div>
        
        <script>
            document.getElementById('otpForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                const email = document.getElementById('email').value;
                const resultDiv = document.getElementById('result');
                
                resultDiv.innerHTML = '<p>🔄 Sending OTP...</p>';
                
                try {
                    const formData = new FormData();
                    formData.append('email', email);
                    
                    const response = await fetch('/auth/test-otp', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        resultDiv.innerHTML = `
                            <div class="result success">
                                <h3>✅ Success!</h3>
                                <p><strong>OTP Code:</strong> ${data.otp_code}</p>
                                <p>Check your email: ${email}</p>
                                <p>Also check the console output and otp_codes.txt file</p>
                            </div>
                        `;
                    } else {
                        resultDiv.innerHTML = `
                            <div class="result error">
                                <h3>❌ Failed</h3>
                                <p>Error: ${data.error || 'Unknown error'}</p>
                            </div>
                        `;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `
                        <div class="result error">
                            <h3>❌ Error</h3>
                            <p>Network error: ${error.message}</p>
                        </div>
                    `;
                }
            });
        </script>
    </body>
    </html>
    '''

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('public.landing'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile management"""
    user = User.get_by_id(session['user_id'])
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        # Update profile
        update_data = {
            'first_name': request.form.get('first_name', '').strip(),
            'last_name': request.form.get('last_name', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'address': request.form.get('address', '').strip()
        }
        
        # Remove empty values
        update_data = {k: v for k, v in update_data.items() if v}
        
        if User.update(session['user_id'], **update_data):
            flash('Profile updated successfully!', 'success')
        else:
            flash('Failed to update profile.', 'error')
        
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html', user=user)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password"""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        user = User.get_by_id(session['user_id'])
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('auth.login'))
        
        # Verify current password
        if not User.authenticate(user['email'], form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return render_template('auth/change_password.html', form=form)
        
        # Update password
        if User.update_password(session['user_id'], form.new_password.data):
            flash('Password changed successfully!', 'success')
            return redirect(url_for('auth.profile'))
        else:
            flash('Failed to change password.', 'error')
    
    return render_template('auth/change_password.html', form=form)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@anonymous_required
def forgot_password():
    """Password reset request"""
    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        email = form.email.data.strip()
        user = User.get_by_email(email)
        
        if user:
            # Generate reset token
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Store token in database (you might want to create a separate table for this)
            # For now, we'll use a simple approach
            session[f'reset_token_{user["id"]}'] = {
                'token_hash': token_hash,
                'expires': (datetime.now() + timedelta(hours=1)).isoformat()
            }
            
            # In a real application, you'd send an email here
            flash(f'Password reset instructions have been sent to {email}. Reset link (for demo): /auth/reset-password/{user["id"]}/{token}', 'info')
        else:
            # Don't reveal whether email exists or not
            flash(f'If an account with {email} exists, password reset instructions have been sent.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html', form=form)

@auth_bp.route('/reset-password/<int:user_id>/<token>', methods=['GET', 'POST'])
@anonymous_required
def reset_password(user_id, token):
    """Password reset form"""
    # Verify token
    session_key = f'reset_token_{user_id}'
    if session_key not in session:
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    token_data = session[session_key]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    if (token_hash != token_data['token_hash'] or 
        datetime.now() > datetime.fromisoformat(token_data['expires'])):
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    form = PasswordResetForm()
    if form.validate_on_submit():
        if User.update_password(user_id, form.password.data):
            # Clear the reset token
            session.pop(session_key, None)
            flash('Password reset successfully! Please log in with your new password.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Failed to reset password.', 'error')
    
    return render_template('auth/reset_password.html', form=form)
