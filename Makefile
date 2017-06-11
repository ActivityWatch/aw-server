.PHONY: build

build:
	pip install mypy
	python3 setup.py install

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python3 -c 'import aw_server'
	make typecheck

typecheck:
	mypy aw_server --ignore-missing-imports

package:
	pyinstaller aw-server.spec --clean --noconfirm

