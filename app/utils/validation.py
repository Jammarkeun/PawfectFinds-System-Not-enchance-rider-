import re
import html
from urllib.parse import urlparse
from flask import request, flash

def sanitize_input(input_string, max_length=None, allow_html=False):
    """Sanitize user input to prevent XSS and other attacks"""
    if not input_string:
        return input_string
    
    # Convert to string if not already
    input_string = str(input_string)
    
    # Remove or escape HTML if not allowed
    if not allow_html:
        input_string = html.escape(input_string)
    
    # Trim whitespace
    input_string = input_string.strip()
    
    # Truncate if max_length specified
    if max_length and len(input_string) > max_length:
        input_string = input_string[:max_length]
    
    return input_string

def validate_email(email):
    """Validate email format"""
    if not email:
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None

def validate_phone(phone):
    """Validate phone number format"""
    if not phone:
        return True  # Phone is optional in most cases
    
    # Remove common phone number characters
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    
    # Check if it contains only digits and is reasonable length
    return cleaned.isdigit() and 7 <= len(cleaned) <= 15

def validate_url(url):
    """Validate URL format"""
    if not url:
        return True  # URL is usually optional
    
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc) and parsed.scheme in ['http', 'https']
    except:
        return False

def validate_price(price):
    """Validate price input"""
    try:
        price_float = float(price)
        return 0 <= price_float <= 999999.99
    except (ValueError, TypeError):
        return False

def validate_quantity(quantity):
    """Validate quantity input"""
    try:
        qty_int = int(quantity)
        return 0 <= qty_int <= 9999
    except (ValueError, TypeError):
        return False

def validate_rating(rating):
    """Validate rating input (1-5)"""
    try:
        rating_int = int(rating)
        return 1 <= rating_int <= 5
    except (ValueError, TypeError):
        return False

def check_sql_injection(input_string):
    """Basic SQL injection pattern detection"""
    if not input_string:
        return False
    
    # Common SQL injection patterns
    dangerous_patterns = [
        r"('|(\\')|(;)|(\\;)|(\\|)|(\\\\))",
        r"((or|OR)\s+(1=1|true))",
        r"((union|UNION)\s+(select|SELECT))",
        r"((drop|DROP)\s+(table|TABLE))",
        r"((insert|INSERT)\s+(into|INTO))",
        r"((delete|DELETE)\s+(from|FROM))",
        r"((update|UPDATE)\s+.+\s+(set|SET))",
        r"(--|#|/\\*|\\*/)",
    ]
    
    input_lower = input_string.lower()
    
    for pattern in dangerous_patterns:
        if re.search(pattern, input_lower):
            return True
    
    return False

def validate_file_upload(file, allowed_extensions=None, max_size=5*1024*1024):
    """Validate file upload"""
    if not file:
        return False, "No file provided"
    
    if file.filename == '':
        return False, "No file selected"
    
    # Check file size
    if hasattr(file, 'content_length') and file.content_length > max_size:
        return False, f"File too large. Maximum size is {max_size//1024//1024}MB"
    
    # Check file extension
    if allowed_extensions:
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            return False, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
    
    return True, "Valid file"

def validate_password_strength(password):
    """Validate password strength"""
    if not password:
        return False, "Password is required"
    
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    
    if len(password) > 128:
        return False, "Password too long"
    
    # Check for at least one letter and one number
    has_letter = bool(re.search(r'[a-zA-Z]', password))
    has_number = bool(re.search(r'\d', password))
    
    if not (has_letter and has_number):
        return False, "Password must contain at least one letter and one number"
    
    return True, "Password is valid"

def sanitize_search_query(query):
    """Sanitize search query to prevent search injection"""
    if not query:
        return ""
    
    # Remove potentially dangerous characters
    query = re.sub(r'[<>"\';\\]', '', query)
    
    # Limit length
    query = query[:200]
    
    # Remove excessive whitespace
    query = ' '.join(query.split())
    
    return query

def validate_pagination_params(page, per_page):
    """Validate pagination parameters"""
    try:
        page = int(page) if page else 1
        per_page = int(per_page) if per_page else 20
        
        # Reasonable limits
        page = max(1, min(page, 10000))
        per_page = max(1, min(per_page, 100))
        
        return page, per_page
    except (ValueError, TypeError):
        return 1, 20

def validate_sort_params(sort_by, allowed_sorts):
    """Validate sort parameters"""
    if not sort_by or sort_by not in allowed_sorts:
        return allowed_sorts[0] if allowed_sorts else 'id'
    return sort_by

def check_honeypot(form_data, honeypot_field='website'):
    """Check honeypot field to detect bots"""
    return form_data.get(honeypot_field, '') != ''

def validate_request_source():
    """Validate request comes from expected source"""
    # Check if request has proper headers
    user_agent = request.headers.get('User-Agent', '')
    
    # Block requests without user agent (likely bots)
    if not user_agent:
        return False
    
    # Check for suspicious user agents
    suspicious_patterns = [
        r'bot',
        r'crawler',
        r'spider',
        r'scraper',
        r'curl',
        r'wget'
    ]
    
    user_agent_lower = user_agent.lower()
    for pattern in suspicious_patterns:
        if re.search(pattern, user_agent_lower):
            # You might want to allow some legitimate bots
            if 'googlebot' in user_agent_lower or 'bingbot' in user_agent_lower:
                return True
            return False
    
    return True

class ValidationError(Exception):
    """Custom validation error exception"""
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(self.message)

def validate_form_data(data, rules):
    """Validate form data against rules
    
    Example usage:
    rules = {
        'email': {'required': True, 'type': 'email'},
        'price': {'required': True, 'type': 'price'},
        'name': {'required': True, 'max_length': 100}
    }
    """
    errors = {}
    
    for field, field_rules in rules.items():
        value = data.get(field)
        
        # Check required fields
        if field_rules.get('required') and not value:
            errors[field] = f"{field.replace('_', ' ').title()} is required"
            continue
        
        if not value:
            continue  # Skip validation for optional empty fields
        
        # Type-specific validation
        field_type = field_rules.get('type')
        if field_type == 'email' and not validate_email(value):
            errors[field] = "Invalid email format"
        elif field_type == 'phone' and not validate_phone(value):
            errors[field] = "Invalid phone format"
        elif field_type == 'url' and not validate_url(value):
            errors[field] = "Invalid URL format"
        elif field_type == 'price' and not validate_price(value):
            errors[field] = "Invalid price"
        elif field_type == 'quantity' and not validate_quantity(value):
            errors[field] = "Invalid quantity"
        elif field_type == 'rating' and not validate_rating(value):
            errors[field] = "Rating must be between 1 and 5"
        
        # Length validation
        max_length = field_rules.get('max_length')
        if max_length and len(str(value)) > max_length:
            errors[field] = f"{field.replace('_', ' ').title()} is too long (max {max_length} characters)"
        
        min_length = field_rules.get('min_length')
        if min_length and len(str(value)) < min_length:
            errors[field] = f"{field.replace('_', ' ').title()} is too short (min {min_length} characters)"
        
        # SQL injection check
        if check_sql_injection(str(value)):
            errors[field] = "Invalid characters detected"
    
    return errors