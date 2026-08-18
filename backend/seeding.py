# seed_requests.py
import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.append(os.path.abspath("."))

from app.services.parser_service import parse_changed_files
from app.db.graph_ops import save_parsed_ast_to_neo4j

# UPDATE THIS: Use an absolute path to your cloned requests directory
# Example: "/Users/yourname/projects/requests" or "C:/Users/yourname/projects/requests"
REQUESTS_REPO_PATH = os.path.abspath("/Users/sitanshusingh/Downloads/requests")
REQUESTS_REPO_NAME = "psf/requests"

async def main():
    print("\n================ STARTING DIAGNOSTIC SEED ================")
    print(f"[CHECK 1] Target Directory: {REQUESTS_REPO_PATH}")
    
    # Check 1: Does path exist?
    if not os.path.exists(REQUESTS_REPO_PATH):
        print(f"❌ [CHECK 1 FAILED] Directory does NOT exist at {REQUESTS_REPO_PATH}")
        print("FIX: Update REQUESTS_REPO_PATH to the absolute path of your cloned requests repo.")
        return
    print("✅ [CHECK 1 PASSED] Directory exists.")

    # Check 2: Scan for Python files
    files_to_parse = []
    for root, _, files in os.walk(REQUESTS_REPO_PATH):
        if any(ignored in root for ignored in [".git", "__pycache__", "venv", ".venv", "build"]):
            continue
        for f in files:
            if f.endswith(".py"):
                files_to_parse.append(os.path.join(root, f))

    print(f"[CHECK 2] Scanning files... Found {len(files_to_parse)} .py files.")
    if len(files_to_parse) == 0:
        print("❌ [CHECK 2 FAILED] No .py files found in this folder!")
        return
    print(f"✅ [CHECK 2 PASSED] Sample file path: {files_to_parse[0]}")

    # Check 3: Run Tree-sitter parser
    print("\n[CHECK 3] Running Tree-sitter parser on files...")
    try:
        parsed_data = await parse_changed_files(files_to_parse)
    except Exception as e:
        print(f"❌ [CHECK 3 FAILED] Tree-sitter threw an exception: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"Completed parsing. Returned {len(parsed_data) if parsed_data else 0} results.")
    
    if not parsed_data:
        print("❌ [CHECK 3 FAILED] parse_changed_files returned an empty list []!")
        return
    
    # Inspect first record
    sample_record = parsed_data[0]
    print("✅ [CHECK 3 PASSED] Sample parsed record:")
    print(f"   - File: {sample_record.get('file_path')}")
    print(f"   - Defined Functions: {sample_record.get('defined_functions')}")
    print(f"   - Outgoing Calls: {sample_record.get('outgoing_calls')}")

    # Check 4: Save to Neo4j
    print("\n[CHECK 4] Saving AST records to Neo4j...")
    try:
        await save_parsed_ast_to_neo4j(
            parsed_data,
            repo_name=REQUESTS_REPO_NAME,
            replace_existing=True,
        )
        print("✅ [CHECK 4 PASSED] Database write finished!")
    except Exception as e:
        print(f"❌ [CHECK 4 FAILED] Neo4j write failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n================ DIAGNOSTIC SEED COMPLETE ================\n")

if __name__ == "__main__":
    asyncio.run(main())
