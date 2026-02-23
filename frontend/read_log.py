
import os

files = ['playwright_log.txt']
for f in files:
    if os.path.exists(f):
        print(f"--- Reading {f} ---")
        content = ""
        # Try UTF-16 first (PowerShell default)
        try:
            content = open(f, encoding='utf-16').read()
            print("Read as UTF-16")
        except:
            try:
                content = open(f, encoding='utf-8', errors='replace').read()
                print("Read as UTF-8")
            except:
                pass
        
        if content:
            found = False
            for line in content.splitlines():
                 if "API RESPONSE" in line or "PAGE LOG" in line or "API BODY" in line or "LOGIN" in line:
                    print(line.strip())
                    found = True
            if not found:
                print("No relevant logs found.")
                print("First 5 lines:")
                print("\n".join(content.splitlines()[:5]))
        else:
            print("Failed to read file.")

