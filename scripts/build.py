"""Build a portable, dependency-free zipapp."""
from pathlib import Path
import shutil
import tempfile
import zipapp
root=Path(__file__).resolve().parents[1]
out=root/'dist'; out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as d:
    stage=Path(d)
    shutil.copytree(root/'gateway_cli',stage/'gateway_cli',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (stage/'__main__.py').write_text('from gateway_cli.cli import main\nraise SystemExit(main())\n', encoding='utf-8')
    zipapp.create_archive(stage,out/'gateway-cli.pyz',interpreter='/usr/bin/env python3',compressed=True)
print(out/'gateway-cli.pyz')
