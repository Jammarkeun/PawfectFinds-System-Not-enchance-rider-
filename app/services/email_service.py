"""
Email Service for Pawfect Finds
Uses Gmail SMTP for sending emails
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

logger = logging.getLogger(__name__)

class EmailService:
    """Email service using Gmail SMTP"""
    
    @staticmethod
    def send_otp_email(recipient_email: str, otp_code: str) -> bool:
        """
        Send OTP email using Gmail SMTP.
        Returns True if successful, False otherwise.
        """
        try:
            # Get email configuration
            sender_email = current_app.config.get('MAIL_DEFAULT_SENDER') or current_app.config.get('MAIL_USERNAME')
            sender_password = current_app.config.get('MAIL_PASSWORD')
            
            # Debug logging
            logger.info(f"Attempting to send email to {recipient_email}")
            logger.info(f"Using sender email: {sender_email}")
            
            if not sender_email or not sender_password:
                logger.error("=== Email Configuration Error ===")
                logger.error(f"MAIL_DEFAULT_SENDER: {current_app.config.get('MAIL_DEFAULT_SENDER')}")
                logger.error(f"MAIL_USERNAME: {current_app.config.get('MAIL_USERNAME')}")
                logger.error(f"MAIL_PASSWORD: {'[SET]' if current_app.config.get('MAIL_PASSWORD') else '[NOT SET]'}")
                logger.error("==============================")
                return False
                
            # Ensure email is in the correct format
            if isinstance(sender_email, tuple):
                sender_email = sender_email[1]  # Get email from (name, email) tuple
            
            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = 'Your Pawfect Finds Verification Code'
            
            # Format the sender to show 'Pawfect Finds' in Gmail
            sender_name = 'Pawfect Finds'
            message['From'] = f'"{sender_name}" <{sender_email}>'
            message['To'] = recipient_email
            
            # Create HTML content
            html = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #6D4C41;">Verification Code</h2>
                        <p>Hello,</p>
                        <p>Your verification code is:</p>
                        <div style="background: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                            <h1 style="color: #6D4C41; font-size: 32px; margin: 0; letter-spacing: 5px;">{otp_code}</h1>
                        </div>
                        <p>Enter this code in the app to complete your signup.</p>
                        <p>This code will expire in 10 minutes.</p>
                        <p style="color: #666; font-size: 12px; margin-top: 30px;">
                            If you didn't request this, you can safely ignore this email.<br>
                            — Pawfect Finds
                        </p>
                    </div>
                </body>
            </html>
            """
            
            # Attach HTML content
            message.attach(MIMEText(html, 'html'))
            
            # Send email using SMTP
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(message)
                
            logger.info(f"OTP email sent to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send OTP email: {e}")
            return False
            
            subject = "Your Pawfect Finds Verification Code"
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #6D4C41;">Verification Code</h2>
                        <p>Hello,</p>
                        <p>Your verification code is:</p>
                        <div style="background: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                            <h1 style="color: #6D4C41; font-size: 32px; margin: 0; letter-spacing: 5px;">{otp_code}</h1>
                        </div>
                        <p>Enter this code in the app to complete your signup.</p>
                        <p>This code will expire in 10 minutes.</p>
                        <p style="color: #666; font-size: 12px; margin-top: 30px;">
                            If you didn't request this, you can safely ignore this email.<br>
                            — Pawfect Finds
                        </p>
                    </div>
                </body>
            </html>
            """
            
            text_content = f"""Hello,

Your verification code is: {otp_code}

Enter this code in the app to complete your signup.

This code will expire in 10 minutes.

If you didn't request this, you can ignore this email.

— Pawfect Finds"""
            
            payload = {
                "personalizations": [{
                    "to": [{"email": recipient_email}]
                }],
                "from": {
                    "email": sender_email,
                    "name": sender_name
                },
                "subject": subject,
                "content": [
                    {
                        "type": "text/plain",
                        "value": text_content
                    },
                    {
                        "type": "text/html",
                        "value": html_content
                    }
                ]
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 202:
                logger.info(f"SendGrid: OTP email sent successfully to {recipient_email}")
                return True
            else:
                logger.error(f"SendGrid API error: {response.status_code} - {response.text}")
                return EmailService._send_via_fallback(recipient_email, otp_code)
                
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return EmailService._send_via_fallback(recipient_email, otp_code)
    
    @staticmethod
    def _send_via_mailgun(recipient_email: str, otp_code: str) -> bool:
        """Send email via Mailgun API"""
        try:
            api_key = current_app.config.get('MAILGUN_API_KEY')
            domain = current_app.config.get('MAILGUN_DOMAIN')
            sender_email = current_app.config.get('EMAIL_FROM', f'noreply@{domain}')
            sender_name = current_app.config.get('EMAIL_FROM_NAME', 'Pawfect Finds')
            
            if not api_key or not domain:
                logger.warning("Mailgun API key or domain not configured")
                return EmailService._send_via_fallback(recipient_email, otp_code)
            
            url = f"https://api.mailgun.net/v3/{domain}/messages"
            
            subject = "Your Pawfect Finds Verification Code"
            text_content = f"""Hello,

Your verification code is: {otp_code}

Enter this code in the app to complete your signup.

This code will expire in 10 minutes.

If you didn't request this, you can ignore this email.

— Pawfect Finds"""
            
            response = requests.post(
                url,
                auth=("api", api_key),
                data={
                    "from": f"{sender_name} <{sender_email}>",
                    "to": recipient_email,
                    "subject": subject,
                    "text": text_content
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Mailgun: OTP email sent successfully to {recipient_email}")
                return True
            else:
                logger.error(f"Mailgun API error: {response.status_code} - {response.text}")
                return EmailService._send_via_fallback(recipient_email, otp_code)
                
        except Exception as e:
            logger.error(f"Mailgun error: {e}")
            return EmailService._send_via_fallback(recipient_email, otp_code)
    
    @staticmethod
    def _send_via_resend(recipient_email: str, otp_code: str) -> bool:
        """Send email via Resend API"""
        try:
            api_key = current_app.config.get('RESEND_API_KEY')
            sender_email = current_app.config.get('EMAIL_FROM', 'noreply@pawfectfinds.com')
            sender_name = current_app.config.get('EMAIL_FROM_NAME', 'Pawfect Finds')
            
            if not api_key:
                logger.warning("Resend API key not configured")
                return EmailService._send_via_fallback(recipient_email, otp_code)
            
            url = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            subject = "Your Pawfect Finds Verification Code"
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #6D4C41;">Verification Code</h2>
                        <p>Hello,</p>
                        <p>Your verification code is:</p>
                        <div style="background: #f5f5f5; padding: 20px; text-align: center; margin: 20px 0;">
                            <h1 style="color: #6D4C41; font-size: 32px; margin: 0; letter-spacing: 5px;">{otp_code}</h1>
                        </div>
                        <p>Enter this code in the app to complete your signup.</p>
                        <p>This code will expire in 10 minutes.</p>
                        <p style="color: #666; font-size: 12px; margin-top: 30px;">
                            If you didn't request this, you can safely ignore this email.<br>
                            — Pawfect Finds
                        </p>
                    </div>
                </body>
            </html>
            """
            
            payload = {
                "from": f"{sender_name} <{sender_email}>",
                "to": [recipient_email],
                "subject": subject,
                "html": html_content
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Resend: OTP email sent successfully to {recipient_email}")
                return True
            else:
                logger.error(f"Resend API error: {response.status_code} - {response.text}")
                return EmailService._send_via_fallback(recipient_email, otp_code)
                
        except Exception as e:
            logger.error(f"Resend error: {e}")
            return EmailService._send_via_fallback(recipient_email, otp_code)
    
    @staticmethod
    def _send_via_smtp(recipient_email: str, otp_code: str) -> bool:
        """Send email via SMTP (fallback method)"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.utils import formataddr
            
            mail_server = current_app.config.get('MAIL_SERVER', 'smtp.gmail.com')
            mail_port = int(current_app.config.get('MAIL_PORT', 587))
            mail_use_tls = bool(current_app.config.get('MAIL_USE_TLS', True))
            mail_username = current_app.config.get('MAIL_USERNAME')
            mail_password = current_app.config.get('MAIL_PASSWORD')
            sender_name = current_app.config.get('EMAIL_FROM_NAME', 'Pawfect Finds')
            sender_email = current_app.config.get('EMAIL_FROM', mail_username)
            
            if not mail_username or not mail_password:
                return EmailService._send_via_fallback(recipient_email, otp_code)
            
            message = MIMEMultipart("alternative")
            message["Subject"] = "Your Pawfect Finds Verification Code"
            message["From"] = formataddr((sender_name, sender_email or mail_username))
            message["To"] = recipient_email
            
            text_content = f"""Hello,

Your verification code is: {otp_code}

Enter this code in the app to complete your signup.

This code will expire in 10 minutes.

If you didn't request this, you can ignore this email.

— Pawfect Finds"""
            
            part = MIMEText(text_content, "plain")
            message.attach(part)
            
            with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
                if mail_use_tls:
                    server.starttls()
                server.login(mail_username, mail_password)
                server.sendmail(sender_email or mail_username, [recipient_email], message.as_string())
            
            logger.info(f"SMTP: OTP email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            return EmailService._send_via_fallback(recipient_email, otp_code)
    
    @staticmethod
    def _send_via_fallback(recipient_email: str, otp_code: str) -> bool:
        """Fallback: Save OTP to file and console"""
        try:
            import os
            from datetime import datetime
            
            otp_file = os.path.join(current_app.root_path, 'otp_codes.txt')
            
            with open(otp_file, 'a', encoding='utf-8') as f:
                f.write(f"{recipient_email}: {otp_code} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            logger.info(f"OTP saved to file for {recipient_email}: {otp_code}")
            print(f"\n🔐 OTP for {recipient_email}: {otp_code}")
            print(f"📁 OTP also saved to: {otp_file}")
            return True
        except Exception as e:
            logger.error(f"Fallback OTP method failed: {e}")
            print(f"\n🔐 OTP for {recipient_email}: {otp_code}")
            return True

