# seed_requests.py
import asyncio
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.append(os.path.abspath("."))

from app.services.batch_parsing import parse_changed_files
from app.services.source_identity import identify_parsed_source
from app.services.graph_ingestion import ingest_identified_files

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
        parsed_batch = await parse_changed_files(files_to_parse)
        parsed_sources = parsed_batch.files
        if len(parsed_sources) != len(files_to_parse):
            raise RuntimeError(
                "Full ingestion aborted because a discovered source file could not be parsed"
            )
        repository_root = Path(REQUESTS_REPO_PATH).resolve()
        identified_files = [
            identify_parsed_source(
                parsed_source,
                repository=REQUESTS_REPO_NAME,
                file_path=Path(parsed_source.file_path)
                .resolve()
                .relative_to(repository_root)
                .as_posix(),
            )
            for parsed_source in parsed_sources
        ]
    except Exception as e:
        print(f"❌ [CHECK 3 FAILED] Tree-sitter threw an exception: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"Completed parsing. Returned {len(parsed_sources)} results.")
    
    if not parsed_sources:
        print("❌ [CHECK 3 FAILED] parse_changed_files returned no parsed files!")
        return
    
    # Inspect first record
    sample_record = parsed_sources[0]
    print("✅ [CHECK 3 PASSED] Sample parsed record:")
    print(f"   - File: {sample_record.file_path}")
    print(f"   - Defined Functions: {[f.name for f in sample_record.functions]}")
    print(f"   - Outgoing Calls: {list(sample_record.outgoing_calls)}")

    # Check 4: Save to Neo4j
    print("\n[CHECK 4] Saving AST records to Neo4j...")
    try:
        await ingest_identified_files(
            identified_files,
            repo_name=REQUESTS_REPO_NAME,
            replace_existing=True,
            total_repo_tokens=parsed_batch.source_tokens,
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
