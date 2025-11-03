from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from flask_socketio import SocketIO
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize SocketIO globally (IMPORTANT: Only initialize once!)
socketio = SocketIO()

# Local application imports (moved inside create_app to avoid import-time issues)
# DO NOT import blueprints here at module level

def create_app():
    """Application factory function"""
    from flask_socketio import join_room, leave_room, emit
    from datetime import timedelta

    # Import models and services inside create_app
    from app.models.user import User
    from app.services.database import Database
    from config.config import Config

    app = Flask(__name__, static_folder='static')
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=30)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    app.config.from_object(Config)

    # Initialize extensions
    db = Database()
    csrf = CSRFProtect(app)
    
    # Initialize SocketIO with app (only once!)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # ✅ IMPORT BLUEPRINTS INSIDE create_app() — THIS FIXES THE 404 ISSUE
    from app.controllers.auth_controller import auth_bp
    from app.controllers.admin_controller import admin_bp
    from app.controllers.seller_controller import seller_bp
    from app.controllers.user_controller import user_bp
    from app.controllers.public_controller import public_bp
    from app.controllers.cart_controller import cart_bp
    from app.controllers.order_controller import order_bp
    from app.controllers.search_controller import search_bp
    from app.controllers.review_controller import review_bp
    from app.controllers.rider_controller import rider_bp

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(seller_bp, url_prefix='/seller')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(public_bp, url_prefix='/')
    app.register_blueprint(cart_bp, url_prefix='/cart')
    app.register_blueprint(order_bp, url_prefix='/order')
    app.register_blueprint(search_bp, url_prefix='/search')
    app.register_blueprint(review_bp, url_prefix='/review')
    app.register_blueprint(rider_bp, url_prefix='/rider')
    
    # IMPORTANT: Exempt rider API routes from CSRF protection
    csrf.exempt(rider_bp)

    # Handle CSRF errors gracefully
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        app.logger.error(f"CSRF error: {e.description}")
        flash('Your session expired or the form is invalid. Please try again.', 'error')
        return render_template('errors/403.html'), 403

    # Create tables when the application starts
    with app.app_context():
        db.create_tables()

    # Cache headers
    @app.after_request
    def add_cache_headers(response):
        if request.path.startswith('/static/'):
            response.headers.setdefault('Cache-Control', 'public, max-age=2592000, immutable')
        return response

    # Inject current user globally in templates
    @app.context_processor
    def inject_user():
        if 'user_id' in session:
            user = User.get_by_id(session['user_id'])
            return dict(current_user=user, csrf_token_value=generate_csrf())
        return dict(current_user=None, csrf_token_value=generate_csrf())

    # Template filters for images and currency
    @app.template_filter('image_url')
    def image_url_filter(image_url):
        if not image_url:
            return 'https://via.placeholder.com/300x200?text=No+Image'
        if image_url.startswith(('http://', 'https://', '/static/')):
            return image_url
        if image_url.startswith('uploads/'):
            return f'/static/{image_url}'
        return url_for('static', filename=image_url)

    @app.template_filter('php')
    def php_currency(value):
        try:
            return f"₱{float(value or 0):,.2f}"
        except Exception:
            return "₱0.00"

    DISCOUNT_PERCENTAGE = 5  # 5% discount

    @app.template_filter('apply_discount')
    def apply_discount(value):
        try:
            amount = float(value or 0)
            discounted = amount * (1 - DISCOUNT_PERCENTAGE / 100)
            return round(discounted, 2)
        except Exception:
            return value

    # Routes
    @app.route('/')
    def index():
        return redirect(url_for('public.landing'))

    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template('errors/500.html'), 500
    
    # SocketIO events for rider real-time updates
    @socketio.on('connect')
    def handle_connect():
        print(f'✓ Client connected: {request.sid}')

    @socketio.on('disconnect')
    def handle_disconnect():
        print(f'✗ Client disconnected: {request.sid}')

    @socketio.on('join')
    def handle_join(data):
        room = data.get('room')
        if room:
            join_room(room)
            print(f'✓ Client {request.sid} joined room: {room}')

    @socketio.on('rider_online')
    def handle_rider_online(data):
        rider_id = data.get('rider_id')
        if rider_id:
            join_room(f'rider_{rider_id}')
            join_room('riders_room')
            join_room('available_orders')
            print(f'✓ Rider {rider_id} is online (SID: {request.sid})')
            emit('connection_confirmed', {'rider_id': rider_id}, room=request.sid)

    @socketio.on('order_accepted')
    def handle_order_accepted(data):
        print(f'✓ Order accepted event: {data}')
        emit('order_taken', data, room='available_orders', broadcast=True)

    return app


app = create_app()

if __name__ == '__main__':
    # Define host and port
    host = '127.0.0.1'
    port = 5000

    # Print the URL clearly in the console
    print(f"\n{'='*50}")
    print(f"🚀 PawfectFinds Server Starting...")
    print(f"{'='*50}")
    print(f"📍 URL: http://{host}:{port}")
    print(f"🔌 SocketIO: Enabled")
    print(f"🔐 CSRF: Enabled (Rider routes exempted)")
    print(f"{'='*50}\n")

    # Run the app with SocketIO
    socketio.run(app, debug=True, host=host, port=port, allow_unsafe_werkzeug=True)