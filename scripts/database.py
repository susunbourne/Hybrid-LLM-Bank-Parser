import mysql.connector
from mysql.connector import Error

import pandas as pd


class DatabaseManager:
    def __init__(self, host, user, password, database, port = 3307):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port

    def get_connection(self):
        try:
            connection = mysql.connector.connect(
                host = self.host,
                port = self.port,
                user = self.user,
                password = self.password,
                database = self.database
            )
            if not connection.is_connected():
                raise ConnectionError("Database created but not connected.")
            return connection
        except Error as e:
            raise ConnectionError(f"Error while connecting to MySQL: {e}") from e
        
    def close_connection(self, connection = None, cursor = None):
        try:
            if cursor is not None:
                cursor.close()
        finally:
            if connection is not None and connection.is_connected():
                connection.close()

    def execute_query(self, sql, params = None, fetch = False, many = False, dictionary = True):
        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary = dictionary)

            if many:
                cursor.executemany(sql, params or [])
            else:
                cursor.execute(sql, params or ())
            
            if fetch:
                return cursor.fetchall()
            
            connection.commit()
            return cursor.rowcount
        except Error as e:
            if connection is not None and connection.is_connected():
                connection.rollback()
            raise RuntimeError(f"Database query failed: {e}") from e
        finally:
            self.close_connection(connection, cursor)

            
    def create_database(self):
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(
                host = self.host,
                port = self.port,
                user = self.user,
                password = self.password
            )
            cursor = connection.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            connection.commit()
            print(f"Database '{self.database}' is ready.")
            

        except Error as e:
            raise RuntimeError(f"Failed to create database: {e}") from e
        finally:
            self.close_connection(connection, cursor)

    def select(self, sql, params = None):
        return self.execute_query(sql, params = params, fetch = True, many = False, dictionary = True)
    
    # def execute(self, sql, params=None):
    #     return self.execute_query(sql, params=params, fetch=False, many=False, dictionary=False)

    # def execute_many(self, sql, data_list):
    #     return self.execute_query(sql, params=data_list, fetch=False, many=True, dictionary=False)



# SQL codes

    def ensure_transactions_table(self):
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            transaction_date DATE NOT NULL,
            description TEXT NOT NULL,
            amount DECIMAL(10,3) NOT NULL,
            category_main VARCHAR(255) NOT NULL,
            category_sub VARCHAR(255) NOT NULL,
            method VARCHAR(255) NOT NULL,
            bank_name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        
        return self.execute_query(
            create_table_sql,
            params = None,
            fetch = False,
            many = False,
            dictionary = False
        )

    def insert_transactions_from_df(self, df: pd.DataFrame, bank_name: str):
        if df is None or df.empty:
            raise ValueError("DataFrame is empty or None. No transactions to insert.")
        
        insert_sql = """
        INSERT INTO transactions (transaction_date, description, amount, category_main, category_sub, method,bank_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        data_list = []
        for _, row in df.iterrows():
            category_main = row.get("category_main", row.get("category", "Other"))
            category_sub = row.get("category_sub", "Unspecified")
            classification_method = row.get("classification_method", "Unknown")
            raw_response = row.get("raw_response", None)
            
            data_list.append(
                (row["transaction_date"],
                row["description"],
                row["amount"],
                category_main,
                category_sub,
                classification_method,
                bank_name
                )
            )
        return self.execute_query(
            insert_sql,
            params = data_list,
            fetch = False,
            many = True,
            dictionary = False
        )