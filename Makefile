.PHONY: aw-webui build install test typecheck package clean

build: aw-webui
	poetry install

aw-webui:
	mkdir -p aw_server/static/
ifeq ($(SKIP_WEBUI),true) # Skip building webui if SKIP_WEBUI is true
	@echo "Skipping building webui"
else
	make --directory=aw-webui build DEV=$(DEV)
	cp -r aw-webui/dist/* aw_server/static/
	# Needed for https://github.com/ActivityWatch/activitywatch/pull/274, works around https://github.com/pypa/pip/issues/6279
	# https://github.com/ActivityWatch/activitywatch/pull/367 Other solutions have been tried but did not actually work.
	# If you aren't sure windows long paths are working, don't remove this
	rm -rf aw-webui/node_modules/.cache
endif

install:
	cp misc/aw-server.service /usr/lib/systemd/user/aw-server.service

test:
	python -c 'import aw_server'
	python -m pytest tests/test_server.py

typecheck:
	python -m mypy aw_server --ignore-missing-imports

package:
	python -m aw_server.__about__
	pyinstaller aw-server.spec --clean --noconfirm

lint-fix:
	black .

clean:
	rm -rf build dist
	rm -rf aw_server/__pycache__
	rm -rf aw_server/static/*
	pip3 uninstall -y aw_server
	make --directory=aw-webui clean
