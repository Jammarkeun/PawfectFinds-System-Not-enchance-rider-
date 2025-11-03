from app.services.database import Database

class Review:
    """Review model for product feedback"""

    @classmethod
    def create(cls, user_id, product_id, rating, comment=None):
        db = Database()
        # Check if user already reviewed this product
        existing = cls.get_by_user_product(user_id, product_id)
        if existing:
            return cls.update(existing['id'], rating, comment)
        query = "INSERT INTO reviews (user_id, product_id, rating, comment) VALUES (%s, %s, %s, %s)"
        review_id = db.execute_query(query, (user_id, product_id, rating, comment))
        return cls.get_by_id(review_id)

    @classmethod
    def get_by_id(cls, review_id):
        db = Database()
        query = """
            SELECT r.*, u.username, u.first_name, u.last_name
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            WHERE r.id = %s
        """
        return db.execute_query(query, (review_id,), fetch=True, fetchone=True)

    @classmethod
    def get_by_user_product(cls, user_id, product_id):
        db = Database()
        query = "SELECT * FROM reviews WHERE user_id = %s AND product_id = %s"
        return db.execute_query(query, (user_id, product_id), fetch=True, fetchone=True)

    @classmethod
    def get_for_product(cls, product_id):
        db = Database()
        query = """
            SELECT r.*, u.username, u.first_name, u.last_name
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            WHERE r.product_id = %s
            ORDER BY r.created_at DESC
        """
        return db.execute_query(query, (product_id,), fetch=True)

    @classmethod
    def update(cls, review_id, rating, comment=None):
        db = Database()
        query = "UPDATE reviews SET rating = %s, comment = %s WHERE id = %s"
        db.execute_query(query, (rating, comment, review_id))
        return cls.get_by_id(review_id)

    @classmethod
    def delete(cls, review_id):
        db = Database()
        query = "DELETE FROM reviews WHERE id = %s"
        db.execute_query(query, (review_id,))
        return True

    @classmethod
    def get_product_average_rating(cls, product_id):
        db = Database()
        query = "SELECT AVG(rating) as avg_rating, COUNT(*) as count FROM reviews WHERE product_id = %s"
        result = db.execute_query(query, (product_id,), fetch=True, fetchone=True)
        if result and result['avg_rating']:
            return {'average': round(float(result['avg_rating']), 1), 'count': result['count']}
        return {'average': 0, 'count': 0}
