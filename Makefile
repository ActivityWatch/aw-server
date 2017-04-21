.PHONY: build

build:
	python3 setup.py install

package:
	pyinstaller aw-server.spec --clean --noconfirm

