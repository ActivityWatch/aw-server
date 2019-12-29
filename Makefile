.PHONY: aw_webui build install test typecheck package clean

ifdef DEV
installcmd := poetry install
else
installcmd := pip install .
endif

build: aw_webui
	$(installcmd)

aw_webui:
	mkdir -p aw_server/static/
ifndef SKIP_WEBUI  # Skip building webui if SKIP_WEBUI is defined
	make --directory=aw-webui build DEV=$(DEV)
	cp -r aw-webui/dist/* aw_server/static/
	rm -rf aw-webui/node_modules/.cache  # Needed for https://github.com/ActivityWatch/activitywatch/pull/274, works around https://github.com/pypa/pip/issues/6279
endif

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python3 -c 'import aw_server'
	python3 -m pytest tests/test_server.py

typecheck:
	python3 -m mypy aw_server --ignore-missing-imports

package:
	python3 -m aw_server.__about__
	pyinstaller aw-server.spec --clean --noconfirm

clean:
	rm -rf build dist
	rm -rf aw_server/__pycache__
	rm -rf aw_server/static/*
	pip3 uninstall -y aw_server
	make --directory=aw-webui clean
