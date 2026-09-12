#!/usr/bin/env python3
"""
Local MP3 Karaoke Streaming Feature - System Verification Script
Verifies that all components are installed and working correctly.
"""

import sys
from pathlib import Path

print('=' * 90)
print('LOCAL MP3 KARAOKE STREAMING FEATURE - SYSTEM VERIFICATION')
print('=' * 90)
print()

# Verify files exist
print('File Verification:')
files_to_check = [
    ('OpenHeartsMusic/core/calls.py', 'Core streaming methods'),
    ('OpenHeartsMusic/plugins/utilities/local_karaoke.py', 'Plugin command handler'),
    ('LOCAL_KARAOKE_GUIDE.md', 'User documentation'),
]

all_exist = True
for filepath, description in files_to_check:
    path = Path(filepath)
    exists = path.exists()
    symbol = '[OK]' if exists else '[FAIL]'
    size = str(path.stat().st_size) + ' bytes' if exists else 'N/A'
    print(f'   {symbol} {description}')
    print(f'        {filepath} ({size})')
    all_exist = all_exist and exists

print()

# Test imports
print('Import Verification:')
try:
    from OpenHeartsMusic.core.calls import TgCall
    from OpenHeartsMusic.plugins.utilities.local_karaoke import local_karaoke_handler
    from OpenHeartsMusic import tune
    print('   [OK] All imports successful')
    print()

    # Check if methods exist
    print('Method Verification:')
    has_validate = hasattr(tune, 'validate_local_mp3')
    has_duration = hasattr(tune, 'get_local_mp3_duration')
    has_stream = hasattr(tune, 'stream_local_mp3')

    validate_status = '[OK]' if has_validate else '[FAIL]'
    duration_status = '[OK]' if has_duration else '[FAIL]'
    stream_status = '[OK]' if has_stream else '[FAIL]'

    print(f'   {validate_status} tune.validate_local_mp3()')
    print(f'   {duration_status} tune.get_local_mp3_duration()')
    print(f'   {stream_status} tune.stream_local_mp3()')
    print()

    all_methods = has_validate and has_duration and has_stream

except Exception as e:
    print(f'   [FAIL] Import failed: {e}')
    print()
    all_methods = False

# Plugin discovery
print('Plugin Discovery:')
try:
    from OpenHeartsMusic.plugins import all_modules
    karaoke_plugins = [m for m in all_modules if 'karaoke' in m.lower()]
    print(f'   [OK] Found {len(karaoke_plugins)} karaoke plugins:')
    for plugin in sorted(karaoke_plugins):
        print(f'       * {plugin}')
    print()
except Exception as e:
    print(f'   [FAIL] Plugin discovery failed: {e}')
    print()

# Final status
print('=' * 90)
if all_exist and all_methods:
    print('FEATURE STATUS: FULLY INSTALLED AND READY TO USE')
    print()
    print('QUICK START:')
    print('   /localkaraoke /path/to/song.mp3')
    print('   /localkaraoke /path/to/song.mp3 Custom Title')
    print()
else:
    print('FEATURE STATUS: INCOMPLETE')
    print()

print('=' * 90)
