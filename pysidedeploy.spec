[app]
title = VideoCompare
project_dir = .
input_file = main.py
exec_directory = dist
project_file = pyproject.toml
icon = src/video_compare/assets/app.ico

[python]
python_path = .venv/Scripts/python.exe
packages = Nuitka==4.1.1

[qt]
qml_files = 
excluded_qml_plugins = 
modules = 
plugins = platforms,imageformats,styles

[nuitka]
mode = standalone
extra_args = --quiet --noinclude-qt-translations --include-package=video_compare --include-package-data=video_compare --include-package=imagecodecs --assume-yes-for-downloads

