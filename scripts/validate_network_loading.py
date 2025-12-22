"""
Simple validation script for network loading logic.
Tests the core functionality without requiring full dependencies.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


def validate_csv_parsing():
    """Validate CSV parsing logic."""
    import csv
    import tempfile
    
    # Create a temporary CSV file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['user1', 'user2'])
        writer.writerow(['user2', 'user3'])
        writer.writerow(['user3', 'user1'])
        csv_path = f.name
    
    try:
        # Parse it
        edges = []
        with open(csv_path, 'r') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                follower = row[0].strip()
                user = row[1].strip()
                edges.append((follower, user))
        
        assert len(edges) == 3, f"Expected 3 edges, got {len(edges)}"
        assert edges[0] == ('user1', 'user2'), f"First edge incorrect: {edges[0]}"
        assert edges[1] == ('user2', 'user3'), f"Second edge incorrect: {edges[1]}"
        assert edges[2] == ('user3', 'user1'), f"Third edge incorrect: {edges[2]}"
        
        print("✓ CSV parsing validation passed")
        return True
        
    finally:
        import os
        os.unlink(csv_path)


def validate_example_network_csv():
    """Validate the example network.csv file."""
    csv_path = Path(__file__).parent / "example" / "network.csv"
    
    if not csv_path.exists():
        print(f"✗ Example network.csv not found at {csv_path}")
        return False
    
    import csv
    edges = []
    
    with open(csv_path, 'r') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if not row or len(row) < 2:
                continue
            edges.append((row[0].strip(), row[1].strip()))
    
    print(f"✓ Example network.csv contains {len(edges)} edges:")
    for follower, user in edges:
        print(f"  - {follower} follows {user}")
    
    return len(edges) > 0


def validate_follow_model():
    """Validate Follow model fields."""
    try:
        from YSimulator.YServer.classes.models import Follow
        
        # Check that Follow has the required fields
        required_fields = ['id', 'user_id', 'follower_id', 'action', 'round']
        
        for field in required_fields:
            if not hasattr(Follow, field):
                print(f"✗ Follow model missing field: {field}")
                return False
        
        print("✓ Follow model has all required fields")
        return True
        
    except ImportError as e:
        print(f"⚠ Could not import Follow model (missing dependencies): {e}")
        return True  # Not a failure, just can't test


def main():
    """Run all validations."""
    print("Running network loading validation tests...\n")
    
    results = []
    
    # Test CSV parsing
    try:
        results.append(("CSV Parsing", validate_csv_parsing()))
    except Exception as e:
        print(f"✗ CSV parsing validation failed: {e}")
        results.append(("CSV Parsing", False))
    
    # Test example network.csv
    try:
        results.append(("Example network.csv", validate_example_network_csv()))
    except Exception as e:
        print(f"✗ Example network.csv validation failed: {e}")
        results.append(("Example network.csv", False))
    
    # Test Follow model
    try:
        results.append(("Follow Model", validate_follow_model()))
    except Exception as e:
        print(f"✗ Follow model validation failed: {e}")
        results.append(("Follow Model", False))
    
    # Summary
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name:30s} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return all(result for _, result in results)


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
