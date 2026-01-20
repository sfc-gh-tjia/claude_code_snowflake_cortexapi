#!/usr/bin/env python3
"""
LiteLLM Snowflake Compatibility Patch

This script patches LiteLLM to rename 'max_tokens' to 'max_completion_tokens'
before sending requests to Snowflake Cortex, which doesn't support the
'max_tokens' parameter.

Usage:
    python patches/apply_patch.py         # Apply the patch
    python patches/apply_patch.py --check # Check if patch is applied
    python patches/apply_patch.py --undo  # Remove the patch (restore backup)
"""

import os
import re
import sys
import shutil
import argparse


def get_litellm_openai_path() -> str:
    """Get the path to LiteLLM's openai.py file."""
    try:
        import litellm
        return os.path.join(os.path.dirname(litellm.__file__), "llms", "openai", "openai.py")
    except ImportError:
        print("Error: LiteLLM is not installed")
        print("Install it with: pip install 'litellm[proxy]'")
        sys.exit(1)


PATCH_MARKER = "HACK: FORCE SNOWFLAKE COMPATIBILITY"

PATCH_CODE = '''
                # --- HACK: FORCE SNOWFLAKE COMPATIBILITY ---
                if "max_tokens" in data:
                    data["max_completion_tokens"] = data.pop("max_tokens")
                # -------------------------------------------

                headers, response = await self.make_openai_chat_completion_request('''

ORIGINAL_CODE = '''
                headers, response = await self.make_openai_chat_completion_request('''


def is_patched(filepath: str) -> bool:
    """Check if the file is already patched."""
    with open(filepath, "r") as f:
        return PATCH_MARKER in f.read()


def apply_patch(filepath: str) -> bool:
    """
    Apply the Snowflake compatibility patch.
    
    Returns:
        bool: True if patch was applied, False if already patched
    """
    if is_patched(filepath):
        print("✓ Patch is already applied")
        return False
    
    # Create backup
    backup_path = filepath + ".backup"
    if not os.path.exists(backup_path):
        shutil.copy2(filepath, backup_path)
        print(f"✓ Backup created: {backup_path}")
    
    # Read the file
    with open(filepath, "r") as f:
        content = f.read()
    
    # Count occurrences before patching
    pattern = r'\n                headers, response = await self\.make_openai_chat_completion_request\('
    matches = re.findall(pattern, content)
    
    if not matches:
        print("✗ Could not find the target code pattern")
        print("  LiteLLM version may be incompatible")
        return False
    
    # Apply the patch (replace all occurrences)
    patched_content = re.sub(pattern, PATCH_CODE, content)
    
    # Write back
    with open(filepath, "w") as f:
        f.write(patched_content)
    
    print(f"✓ Patch applied to {len(matches)} location(s)")
    return True


def undo_patch(filepath: str) -> bool:
    """
    Restore the original file from backup.
    
    Returns:
        bool: True if restored, False if no backup found
    """
    backup_path = filepath + ".backup"
    
    if not os.path.exists(backup_path):
        print("✗ No backup file found")
        print(f"  Expected: {backup_path}")
        return False
    
    shutil.copy2(backup_path, filepath)
    print(f"✓ Restored from backup")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Apply or remove the LiteLLM Snowflake compatibility patch"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if patch is applied without making changes"
    )
    parser.add_argument(
        "--undo",
        action="store_true", 
        help="Remove the patch by restoring from backup"
    )
    
    args = parser.parse_args()
    
    filepath = get_litellm_openai_path()
    print(f"LiteLLM file: {filepath}")
    print()
    
    if args.check:
        if is_patched(filepath):
            print("✓ Patch is applied")
            sys.exit(0)
        else:
            print("✗ Patch is NOT applied")
            sys.exit(1)
    
    elif args.undo:
        if undo_patch(filepath):
            print("\nRemember to restart the proxy:")
            print("  pm2 restart claude-proxy")
        sys.exit(0)
    
    else:
        if apply_patch(filepath):
            print("\nRemember to restart the proxy:")
            print("  pm2 restart claude-proxy")
        sys.exit(0)


if __name__ == "__main__":
    main()
