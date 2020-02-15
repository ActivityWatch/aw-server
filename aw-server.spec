# -*- mode: python -*-
# vi: set ft=python :

import os

import aw_core
aw_core_path = os.path.dirname(aw_core.__file__)

import flask_restx
restx_path = os.path.dirname(flask_restx.__file__)

block_cipher = None


a = Analysis(['__main__.py'],
             pathex=[],
             binaries=None,
             datas=[
                ('aw_server/static', 'aw_server/static'),

                (os.path.join(restx_path, 'templates'), 'flask_restx/templates'),
                (os.path.join(restx_path, 'static'), 'flask_restx/static'),
                (os.path.join(aw_core_path, 'schemas'), 'aw_core/schemas')
             ],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='aw-server',
          debug=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='aw-server')
