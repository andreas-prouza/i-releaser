
set -o errexit

# Copies the files of a template directory, without overwriting existing files
copy_templates() {
  mkdir -p "$2"
  for file in "$1"/*; do
    if [ -f "$file" ] && [ ! -e "$2/$(basename "$file")" ]; then
      cp "$file" "$2/"
    fi
  done
}

if [ -d "./.venv" ]; then
  echo "Virtual environment does already exist"
else
  echo "Create virtual environment"
  python3.13 -m venv --system-site-packages ./.venv
fi

echo "Activate virtual environment"
if [ $OSTYPE == 'msys' ] || [ $OSTYPE == 'win32' ] || [ $OSTYPE == 'mingw' ] || [ $OSTYPE == 'mingw32' ]; then
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi

echo "Update pip"
pip install --upgrade pip

echo "Install all requirements"
pip install -r requirements.txt

copy_templates webapp/etc/examples webapp/etc
copy_templates etc/examples etc
copy_templates scripts/examples scripts

# Only in a new installation
if [ ! -d etc/workflows ]; then
  copy_templates etc/examples/workflows etc/workflows
fi
