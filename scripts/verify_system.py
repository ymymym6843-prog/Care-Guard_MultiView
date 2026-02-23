
import os
import subprocess
import sys
from pathlib import Path

def run_command(command, cwd=None):
    print(f"Running: {command}")
    try:
        result = subprocess.run(
            command, 
            cwd=cwd, 
            shell=True, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        print("✅ Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {e.stderr}")
        return False

def check_frontend_types():
    print("\n--- Checking Frontend Types ---")
    return run_command("npm run type-check", cwd="frontend")

def check_backend_tests():
    print("\n--- Checking Backend Tests ---")
    # Using the verified command from Phase 32
    return run_command("venv\\Scripts\\pytest tests/test_api.py tests/test_api_auth.py", cwd="backend")

def check_docs():
    print("\n--- Checking Documentation ---")
    docs_dir = Path("docs")
    required_files = [
        "01_presentation/README_SCREENSHOTS.md",
        # Add other critical docs here if needed
    ]
    
    missing = []
    if not docs_dir.exists():
        print(f"❌ Missing docs directory: {docs_dir}")
        return False
        
    for f in required_files:
        if not (docs_dir / f).exists():
            missing.append(f)
            
    if missing:
        for m in missing:
            print(f"❌ Missing document: {m}")
        return False
        
    print("✅ Docs structure valid")
    return True

def main():
    print("Starting Final System Verification...")
    
    # 1. Frontend
    fe_ok = check_frontend_types()
    
    # 2. Backend
    be_ok = check_backend_tests()
    
    # 3. Docs
    docs_ok = check_docs()
    
    if fe_ok and be_ok and docs_ok:
        print("\n🎉 All systems operational!")
        sys.exit(0)
    else:
        print("\n⚠️  Some checks failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
