import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.domain.dependency_set import DependencySet, DependencyFile


def test_bundle_hash_calculation():
    dep_file1 = DependencyFile(
        relative_path="package.json",
        content=b'{"name": "test", "version": "1.0.0"}'
    )
    
    dep_file2 = DependencyFile(
        relative_path="package-lock.json", 
        content=b'{"lockfileVersion": 2}'
    )
    
    dep_set = DependencySet(
        manager="npm",
        files=[dep_file1, dep_file2],
        node_version="18.0.0",
        npm_version="9.0.0"
    )
    
    bundle_hash = dep_set.calculate_bundle_hash()
    
    assert len(bundle_hash) == 64
    assert all(c in "0123456789abcdef" for c in bundle_hash)
    
    dep_set2 = DependencySet(
        manager="npm",
        files=[dep_file1, dep_file2],
        node_version="18.0.0",
        npm_version="9.0.0"
    )
    
    assert dep_set.calculate_bundle_hash() == dep_set2.calculate_bundle_hash()
    
    dep_set3 = DependencySet(
        manager="npm",
        files=[dep_file1, dep_file2],
        node_version="18.0.1",
        npm_version="9.0.0"
    )
    
    assert dep_set.calculate_bundle_hash() != dep_set3.calculate_bundle_hash()
    
    print("✓ Bundle hash calculation test passed")


def test_file_hashes():
    dep_file1 = DependencyFile(
        relative_path="package.json",
        content=b'{"name": "test", "version": "1.0.0"}'
    )
    
    dep_file2 = DependencyFile(
        relative_path="package-lock.json",
        content=b'{"lockfileVersion": 2}'
    )
    
    dep_set = DependencySet(
        manager="npm",
        files=[dep_file1, dep_file2]
    )
    
    file_hashes = dep_set.get_file_hashes()
    
    assert len(file_hashes) == 2
    assert "package.json" in file_hashes
    assert "package-lock.json" in file_hashes
    assert len(file_hashes["package.json"]) == 64
    assert len(file_hashes["package-lock.json"]) == 64
    
    print("✓ File hashes test passed")


if __name__ == "__main__":
    test_bundle_hash_calculation()
    test_file_hashes()
    print("\nAll tests passed!")