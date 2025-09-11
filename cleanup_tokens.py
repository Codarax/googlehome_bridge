#!/usr/bin/env python3
"""
Token cleanup script for OAuth server
Removes expired tokens from tokens.json with backup and detailed logging
"""

import json
import time
import os
from datetime import datetime

TOKENS_FILE = "tokens.json"

def cleanup_expired_tokens(verbose=True):
    """Clean up expired tokens from tokens.json"""

    if not os.path.exists(TOKENS_FILE):
        if verbose:
            print(f"INFO: No {TOKENS_FILE} found")
        return False

    try:
        # Load current tokens
        with open(TOKENS_FILE, 'r') as f:
            data = json.load(f)

        current_time = int(time.time())
        if verbose:
            print(f"INFO: Current timestamp: {current_time} ({datetime.fromtimestamp(current_time)})")

        # Clean up auth codes
        auth_codes = data.get('auth_codes', {})
        expired_auth_codes = []

        for code, code_data in auth_codes.items():
            expires_at = code_data.get('expires_at', 0)
            if expires_at < current_time:
                expired_auth_codes.append(code)
                if verbose:
                    print(f"EXPIRED: Auth code {code[:20]}... (expired: {datetime.fromtimestamp(expires_at)})")

        for code in expired_auth_codes:
            del auth_codes[code]

        # Clean up access tokens
        access_tokens = data.get('access_tokens', {})
        expired_access_tokens = []

        for token, token_data in access_tokens.items():
            expires_at = token_data.get('expires_at', 0)
            if expires_at < current_time:
                expired_access_tokens.append(token)
                if verbose:
                    print(f"EXPIRED: Access token {token[:20]}... (expired: {datetime.fromtimestamp(expires_at)})")

        for token in expired_access_tokens:
            del access_tokens[token]

        # Clean up refresh tokens
        refresh_tokens = data.get('refresh_tokens', {})
        expired_refresh_tokens = []

        for token, token_data in refresh_tokens.items():
            expires_at = token_data.get('expires_at', 0)
            if expires_at < current_time:
                expired_refresh_tokens.append(token)
                if verbose:
                    print(f"EXPIRED: Refresh token {token[:20]}... (expired: {datetime.fromtimestamp(expires_at)})")

        for token in expired_refresh_tokens:
            del refresh_tokens[token]

        # Check if any cleanup was needed
        total_expired = len(expired_auth_codes) + len(expired_access_tokens) + len(expired_refresh_tokens)

        if total_expired == 0:
            if verbose:
                print("INFO: No expired tokens found - cleanup not needed")
            return True

        # Create backup before saving
        backup_file = f"{TOKENS_FILE}.backup.{int(time.time())}"
        try:
            os.rename(TOKENS_FILE, backup_file)
            if verbose:
                print(f"INFO: Created backup: {backup_file}")
        except Exception as e:
            if verbose:
                print(f"WARNING: Could not create backup: {e}")

        # Save cleaned data
        cleaned_data = {
            'auth_codes': auth_codes,
            'access_tokens': access_tokens,
            'refresh_tokens': refresh_tokens
        }

        with open(TOKENS_FILE, 'w') as f:
            json.dump(cleaned_data, f, indent=2)

        if verbose:
            print("\n✅ CLEANUP COMPLETE:")
            print(f"  - Auth codes removed: {len(expired_auth_codes)}")
            print(f"  - Access tokens removed: {len(expired_access_tokens)}")
            print(f"  - Refresh tokens removed: {len(expired_refresh_tokens)}")
            print(f"  - Total tokens removed: {total_expired}")
            print(f"  - Remaining auth codes: {len(auth_codes)}")
            print(f"  - Remaining access tokens: {len(access_tokens)}")
            print(f"  - Remaining refresh tokens: {len(refresh_tokens)}")

        return True

    except Exception as e:
        if verbose:
            print(f"ERROR: Failed to cleanup tokens: {e}")
        return False

def get_token_stats():
    """Get statistics about current tokens without cleaning"""
    if not os.path.exists(TOKENS_FILE):
        return None

    try:
        with open(TOKENS_FILE, 'r') as f:
            data = json.load(f)

        current_time = int(time.time())
        stats = {
            'total_auth_codes': len(data.get('auth_codes', {})),
            'total_access_tokens': len(data.get('access_tokens', {})),
            'total_refresh_tokens': len(data.get('refresh_tokens', {})),
            'expired_auth_codes': 0,
            'expired_access_tokens': 0,
            'expired_refresh_tokens': 0,
            'current_time': current_time
        }

        # Count expired tokens
        for code_data in data.get('auth_codes', {}).values():
            if code_data.get('expires_at', 0) < current_time:
                stats['expired_auth_codes'] += 1

        for token_data in data.get('access_tokens', {}).values():
            if token_data.get('expires_at', 0) < current_time:
                stats['expired_access_tokens'] += 1

        for token_data in data.get('refresh_tokens', {}).values():
            if token_data.get('expires_at', 0) < current_time:
                stats['expired_refresh_tokens'] += 1

        return stats

    except Exception as e:
        print(f"ERROR: Failed to get token stats: {e}")
        return None

if __name__ == "__main__":
    print("🧹 Starting token cleanup...")
    success = cleanup_expired_tokens(verbose=True)
    if success:
        print("✅ Token cleanup completed successfully!")
    else:
        print("❌ Token cleanup failed!")
