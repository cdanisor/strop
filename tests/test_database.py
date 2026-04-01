"""
Test database functionality for irrigation system
"""
import unittest
import os
import sys
from datetime import datetime

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database import Database

class TestDatabase(unittest.TestCase):
    """Test database functionality."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Use a temporary database for testing
        self.db = Database("test_database.db")
    
    def tearDown(self):
        """Clean up after each test method."""
        # Remove test database file
        if os.path.exists("test_database.db"):
            os.remove("test_database.db")
    
    def test_valve_log_insertion(self):
        """Test inserting valve logs."""
        # Insert a valve log
        result = self.db.insert_valve_log(1, 'on', 30)
        self.assertTrue(result)
        
        # Insert another valve log
        result = self.db.insert_valve_log(2, 'off', None)
        self.assertTrue(result)
        
        # Retrieve logs
        logs = self.db.get_valve_logs()
        self.assertEqual(len(logs), 2)
        
        # Check that we have logs for both valves
        valve_ids = [log['valve_id'] for log in logs]
        self.assertIn(1, valve_ids)
        self.assertIn(2, valve_ids)
        
        # Find the specific logs
        log1 = next(log for log in logs if log['valve_id'] == 1)
        log2 = next(log for log in logs if log['valve_id'] == 2)
        
        # Check first log
        self.assertEqual(log1['operation'], 'on')
        self.assertEqual(log1['duration'], 30)
        
        # Check second log
        self.assertEqual(log2['operation'], 'off')
        self.assertIsNone(log2['duration'])
    
    def test_valve_log_filtering(self):
        """Test retrieving valve logs with filtering."""
        # Insert multiple valve logs
        self.db.insert_valve_log(1, 'on', 30)
        self.db.insert_valve_log(1, 'off', 30)
        self.db.insert_valve_log(2, 'on', 60)
        
        # Get logs for valve 1
        logs = self.db.get_valve_logs(valve_id=1)
        self.assertEqual(len(logs), 2)
        
        # Check that all logs are for valve 1
        for log in logs:
            self.assertEqual(log['valve_id'], 1)
        
        # Get all logs
        logs = self.db.get_valve_logs()
        self.assertEqual(len(logs), 3)
    
    def test_database_initialization(self):
        """Test that database initializes correctly."""
        # Database should be initialized without errors
        self.assertIsNotNone(self.db)
        
        # Test that we can get a connection
        conn = self.db.get_connection()
        self.assertIsNotNone(conn)
        conn.close()

if __name__ == '__main__':
    unittest.main()