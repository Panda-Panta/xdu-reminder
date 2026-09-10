# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [
    ('web/templates', 'web/templates'),
    ('web/static', 'web/static'),
    ('config.example.yaml', '.'),
    ('nssm.exe', '.'),
    ('install_service.bat', '.'),
    ('uninstall_service.bat', '.'),
    ('使用说明.txt', '.'),
]

# 收集 APScheduler 与相关时区模块数据
datas += collect_data_files('apscheduler')
datas += collect_data_files('tzdata')

hiddenimports = [
    'apscheduler',
    'apscheduler.schedulers.background',
    'apscheduler.triggers.cron',
    'apscheduler.triggers.date',
    'apscheduler.triggers.interval',
    'tzlocal',
    'tzdata',
    'pytz',
    'Crypto',
    'Crypto.Cipher.AES',
    'Crypto.Util.Padding',
    'PIL',
    'PIL.Image',
    'httpx',
    'httpcore',
    'loguru',
    'flask',
    'jinja2',
    'yaml',
    'win11toast',
]
hiddenimports += collect_submodules('apscheduler')
hiddenimports += collect_submodules('notifiers')
hiddenimports += collect_submodules('services')
hiddenimports += collect_submodules('reminder')
hiddenimports += collect_submodules('auth')
hiddenimports += collect_submodules('core')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='xdu-reminder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='xdu-reminder',
)
