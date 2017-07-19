.PHONY: build install test typecheck package clean

build:
	pip install . -r requirements.txt

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python3 -c 'import aw_server'
	make typecheck

typecheck:
	mypy aw_server --ignore-missing-imports

package:
	pyinstaller aw-server.spec --clean --noconfirm

clean:
	rm -rf build dist
	rm -rf aw_server/__pycache__
