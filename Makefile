.PHONY: aw_webui build install test typecheck package clean

pip_install_args := . -r requirements.txt --upgrade

ifdef DEV
pip_install_args := --editable $(pip_install_args)
endif

aw_webui:
	make --directory=aw-webui build DEV=$(DEV)
	mkdir -p aw_server/static/
	cp -r aw-webui/dist/* aw_server/static/

build: aw_webui
	pip3 install $(pip_install_args)

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python3 -c 'import aw_server'
	make typecheck

typecheck:
	mypy aw_server --ignore-missing-imports

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
