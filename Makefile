.PHONY: build

build:
	python3 setup.py install

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python3 -c 'import aw_server'

package:
	pyinstaller aw-server.spec --clean --noconfirm

