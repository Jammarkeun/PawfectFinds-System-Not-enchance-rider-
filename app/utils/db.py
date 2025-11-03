"""
Simple MySQL Database Utility
Direct MySQL connection without SQLAlchemy to avoid schema conflicts
"""
import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager
import os

class Database:
    def __init__(self):
        self.config = {
            'host': 'localhost',
            'database': 'pawfect_findsdatabase',
            'user': 'root',
            'password': '',  # Add password if needed
            'charset': 'utf8mb4',
            'autocommit': False
        }
    
    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        connection = None
        try:
            connection = mysql.connector.connect(**self.config)
            yield connection
        except Error as e:
            if connection:
                connection.rollback()
            print(f"Database error: {e}")
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    @contextmanager
    def get_cursor(self, dictionary=True):
        """Get database cursor with context manager"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=dictionary)
            try:
                yield cursor, connection
                connection.commit()
            except Error as e:
                connection.rollback()
                print(f"Database error: {e}")
                raise
            finally:
                cursor.close()
    
    def execute_query(self, query, params=None, fetch=True):
        """Execute a single query"""
        try:
            with self.get_cursor() as (cursor, connection):
                cursor.execute(query, params or ())
                if fetch:
                    return cursor.fetchall()
                return cursor.rowcount
        except Error as e:
            print(f"Query execution error: {e}")
            return None
    
    def execute_many(self, query, params_list):
        """Execute multiple queries with different parameters"""
        try:
            with self.get_cursor() as (cursor, connection):
                cursor.executemany(query, params_list)
                return cursor.rowcount
        except Error as e:
            print(f"Batch query execution error: {e}")
            return None
    
    def get_one(self, query, params=None):
        """Get single row"""
        try:
            with self.get_cursor() as (cursor, connection):
                cursor.execute(query, params or ())
                return cursor.fetchone()
        except Error as e:
            print(f"Query execution error: {e}")
            return None
    
    def get_last_insert_id(self, cursor):
        """Get last inserted ID"""
        return cursor.lastrowid

# Global database instance
db = Database()