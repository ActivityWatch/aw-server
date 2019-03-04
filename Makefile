.PHONY: aw_webui build install test typecheck package clean

pip_install_args := . -r requirements.txt --upgrade

ifdef DEV
pip_install_args := --editable $(pip_install_args)
endif

aw_webui:
	mkdir -p aw_server/static/
ifndef SKIP_WEBUI  # Skip building webui if SKIP_WEBUI is defined
	make --directory=aw-webui build DEV=$(DEV)
	cp -r aw-webui/dist/* aw_server/static/
endif

build: aw_webui
	pip3 install $(pip_install_args)

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	pipenv run python3 -c 'import aw_server'
	pipenv run python3 -m pytest tests/conftest.py tests/test_server.py
	make typecheck

typecheck:
	pipenv run mypy aw_server --ignore-missing-imports

lock:
	pipenv lock -r > requirements.txt
	pipenv lock -r -d > dev-requirements.txt

package:
	make clean
	python3 -m aw_server.__about__
	make build
	pyinstaller aw-server.spec --clean --noconfirm

clean:
	rm -rf build dist
	rm -rf aw_server/__pycache__
	rm -rf aw_server/static/*
	pip3 uninstall -y aw_server
	make --directory=aw-webui clean
