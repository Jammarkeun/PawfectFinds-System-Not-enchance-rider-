"""
Gmail API Service for sending emails
"""
import os
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import logging

# If modifying these scopes, delete the token.json file.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

logger = logging.getLogger(__name__)

class GmailService:
    """Gmail API service for sending emails"""
    
    def __init__(self):
        self.creds = None
        self.service = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize the Gmail API service."""
        # The file token.json stores the user's access and refresh tokens
        token_path = os.path.join(os.path.dirname(__file__), '..', '..', 'token.json')
        creds_path = os.path.join(os.path.dirname(__file__), '..', '..', 'credentials.json')
        
        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        # If there are no (valid) credentials available, let the user log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    raise FileNotFoundError(
                        "credentials.json not found. Please download it from Google Cloud Console and place it in the project root."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(token_path, 'w') as token:
                    token.write(self.creds.to_json())
        
        try:
            self.service = build('gmail', 'v1', credentials=self.creds)
        except Exception as e:
            logger.error(f"Failed to initialize Gmail service: {e}")
            raise
    
    def send_otp_email(self, recipient_email: str, otp_code: str) -> bool:
        """Send an OTP email using Gmail API."""
        if not self.service:
            logger.error("Gmail service not initialized")
            return False
        
        try:
            message = self._create_message(recipient_email, otp_code)
            self._send_message(message)
            logger.info(f"OTP email sent to {recipient_email}")
            return True
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _create_message(self, to: str, otp_code: str) -> dict:
        """Create a message for an email."""
        subject = "Your Pawfect Finds Verification Code"
        message_text = f"""
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
        
        message = MIMEText(message_text, 'html')
        message['to'] = to
        message['from'] = 'Pawfect Finds <noreply@pawfectfinds.com>'
        message['subject'] = subject
        
        return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
    
    def _send_message(self, message: dict) -> dict:
        """Send an email message."""
        try:
            message = (self.service.users().messages()
                     .send(userId="me", body=message).execute())
            return message
        except HttpError as error:
            logger.error(f"Error sending message: {error}")
            raise

# Singleton instance
gmail_service = GmailService()
