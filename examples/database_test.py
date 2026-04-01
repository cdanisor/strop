"""
Simple test to verify database logging functionality
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.database import Database

def test_database_logging():
    """Test that database logging works correctly."""
    print("Testing database logging functionality...")
    
    # Create database instance
    db = Database()
    
    # Test inserting valve logs
    print("Inserting valve logs...")
    db.insert_valve_log(1, 'on', 30)
    db.insert_valve_log(2, 'off', None)
    
    # Test retrieving logs
    print("Retrieving valve logs...")
    logs = db.get_valve_logs()
    
    print(f"Found {len(logs)} logs:")
    for log in logs:
        print(f"  Valve {log['valve_id']}: {log['operation']} at {log['timestamp']} (duration: {log['duration']})")
    
    # Test filtering by valve
    print("\nRetrieving logs for valve 1...")
    valve1_logs = db.get_valve_logs(valve_id=1)
    print(f"Found {len(valve1_logs)} logs for valve 1:")
    for log in valve1_logs:
        print(f"  Valve {log['valve_id']}: {log['operation']} at {log['timestamp']} (duration: {log['duration']})")
    
    print("\nDatabase logging test completed successfully!")

if __name__ == "__main__":
    test_database_logging()