# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
    ['entry.py'],
    pathex=[],
    binaries=[],
    datas=collect_data_files("exifread"),
    hiddenimports=[
        "exifread.tags",
        "exifread.tags.makernote",
        "exifread.heic",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "email", "html", "http", "pydoc"],
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="library-organizer-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon="assets/library-organizer.ico",
    version="version_info.txt",
)
