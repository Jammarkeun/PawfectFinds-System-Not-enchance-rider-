import mysql.connector
from mysql.connector import Error
from config.config import Config
import logging

class Database:
    """Database service class for MySQL operations"""
    
    def __init__(self):
        self.config = Config.DATABASE
        self.connection = None
    
    def init_app(self, app):
        """No-op initializer to satisfy legacy app wiring"""
        # Optionally, override config from app.config if present
        try:
            host = app.config.get('MYSQL_HOST')
            user = app.config.get('MYSQL_USER')
            password = app.config.get('MYSQL_PASSWORD')
            database = app.config.get('MYSQL_DB')
            if host and user and database is not None:
                self.config = {
                    'host': host,
                    'user': user,
                    'password': password,
                    'database': database
                }
        except Exception:
            pass
    
    def connect(self):
        """Establish database connection"""
        try:
            if self.connection is None or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**self.config)
                # Set connection timeout and other options
                self.connection.autocommit = False
                return self.connection
            return self.connection
        except Error as e:
            logging.error(f"Database connection error: {e}")
            raise e
    
    def disconnect(self):
        """Close database connection"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
    
    def execute_query(self, query, params=None, fetch=False, fetchone=False):
        """Execute a SQL query with a fresh connection each time"""
        connection = None
        cursor = None
        try:
            # Create a new connection for each query
            config = self.config.copy()
            config.update({
                'buffered': True,  # Ensure results are buffered
                'consume_results': True  # Consume all results
            })

            # Create a new connection
            connection = mysql.connector.connect(**config)

            # Create a buffered cursor
            cursor = connection.cursor(dictionary=True, buffered=True)

            # Execute the query
            cursor.execute(query, params or ())

            # For SELECT queries, fetch the results
            if fetch or fetchone:
                result = cursor.fetchone() if fetchone else cursor.fetchall()
                # Ensure we consume all results
                if not fetchone:
                    cursor.fetchall()
                cursor.close()
                connection.close()
                return result
            else:
                # For non-SELECT queries, commit and return lastrowid
                connection.commit()
                last_id = cursor.lastrowid
                cursor.close()
                connection.close()
                return last_id
                
        except Error as e:
            logging.error(f"Database query error: {e}")
            if connection and connection.is_connected():
                try:
                    connection.rollback()
                except Error as rollback_error:
                    logging.error(f"Rollback failed: {rollback_error}")
            raise e
            
        finally:
            # Always ensure connections are closed
            try:
                if cursor:
                    cursor.close()
            except:
                pass
                
            try:
                if connection and connection.is_connected():
                    connection.close()
            except:
                pass
    
    def create_database(self):
        """Create the database if it doesn't exist"""
        try:
            # Connect without specifying database
            temp_config = self.config.copy()
            del temp_config['database']
            
            connection = mysql.connector.connect(**temp_config)
            cursor = connection.cursor()
            
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.config['database']}")
            cursor.close()
            connection.close()
            
        except Error as e:
            logging.error(f"Database creation error: {e}")
            raise e
    
    def create_tables(self):
        """Create all necessary tables"""
        self.create_database()
        
        # Users table
        users_table = '''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            phone VARCHAR(20),
            address TEXT,
            role ENUM('user', 'seller', 'admin') DEFAULT 'user',
            status ENUM('active', 'inactive', 'banned') DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        '''
        
        # Seller requests table
        seller_requests_table = '''
        CREATE TABLE IF NOT EXISTS seller_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            business_name VARCHAR(100) NOT NULL,
            business_description TEXT,
            business_address TEXT NOT NULL,
            business_phone VARCHAR(20) NOT NULL,
            tax_id VARCHAR(50),
            status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
            admin_notes TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
        
        # Categories table
        categories_table = '''
        CREATE TABLE IF NOT EXISTS categories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            image_url VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
        
        # Products table
        products_table = '''
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            seller_id INT NOT NULL,
            category_id INT NOT NULL,
            name VARCHAR(200) NOT NULL,
            description TEXT,
            price DECIMAL(10,2) NOT NULL,
            stock_quantity INT DEFAULT 0,
            image_url VARCHAR(255),
            status ENUM('active', 'inactive', 'out_of_stock') DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT
        )
        '''
        
        # Cart table
        cart_table = '''
        CREATE TABLE IF NOT EXISTS cart (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity INT NOT NULL DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            UNIQUE KEY unique_user_product (user_id, product_id)
        )
        '''
        
        # Orders table
        orders_table = '''
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            seller_id INT NOT NULL,
            total_amount DECIMAL(10,2) NOT NULL,
            status ENUM('pending', 'confirmed', 'preparing', 'shipped', 'on_the_way', 'delivered', 'cancelled') DEFAULT 'pending',
            shipping_address TEXT NOT NULL,
            payment_method ENUM('cod', 'online') DEFAULT 'cod',
            payment_status ENUM('pending', 'paid', 'refunded') DEFAULT 'pending',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE RESTRICT
        )
        '''
        
        # Order items table
        order_items_table = '''
        CREATE TABLE IF NOT EXISTS order_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            price_at_time DECIMAL(10,2) NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
        )
        '''
        
        # Reviews table
        reviews_table = '''
        CREATE TABLE IF NOT EXISTS reviews (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            product_id INT NOT NULL,
            rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            UNIQUE KEY unique_user_product_review (user_id, product_id)
        )
        '''
        
        tables = [
            users_table,
            seller_requests_table, 
            categories_table,
            products_table,
            cart_table,
            orders_table,
            order_items_table,
            reviews_table
        ]
        
        for table in tables:
            self.execute_query(table)
        
        # Insert default categories
        self.insert_default_categories()
        
        # Create default admin user
        self.create_default_admin()
    
    def insert_default_categories(self):
        """Insert default pet supply categories"""
        categories = [
            ('Dog Food & Treats', 'Premium dog food and healthy treats'),
            ('Cat Litter & Accessories', 'Cat litter, toys, and accessories'),
            ('Aquariums & Fish Supplies', 'Fish tanks, filters, and aquarium supplies'),
            ('Bird Feeders & Food', 'Bird cages, feeders, and bird food'),
            ('Pet Grooming Products', 'Shampoos, brushes, and grooming tools'),
            ('Pet Health & Wellness', 'Vitamins, supplements, and health products')
        ]
        
        for name, description in categories:
            check_query = "SELECT id FROM categories WHERE name = %s"
            existing = self.execute_query(check_query, (name,), fetch=True, fetchone=True)
            
            if not existing:
                insert_query = "INSERT INTO categories (name, description) VALUES (%s, %s)"
                self.execute_query(insert_query, (name, description))
    
    def create_default_admin(self):
        """Create default admin user"""
        from werkzeug.security import generate_password_hash
        
        admin_email = 'admin@pawfectfinds.com'
        check_query = "SELECT id FROM users WHERE email = %s"
        existing = self.execute_query(check_query, (admin_email,), fetch=True, fetchone=True)
        
        if not existing:
            admin_data = {
                'username': 'admin',
                'email': admin_email,
                'password_hash': generate_password_hash('admin123'),
                'first_name': 'Admin',
                'last_name': 'User',
                'phone': '1234567890',
                'address': 'Admin Office',
                'role': 'admin'
            }
            
            insert_query = '''
                INSERT INTO users (username, email, password_hash, first_name, last_name, phone, address, role)
                VALUES (%(username)s, %(email)s, %(password_hash)s, %(first_name)s, %(last_name)s, %(phone)s, %(address)s, %(role)s)
            '''
            self.execute_query(insert_query, admin_data)
