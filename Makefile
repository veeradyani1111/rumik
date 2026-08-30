PYTHON ?= python

.PHONY: install test itest check run hello kyc

install:
	$(PYTHON) -m pip install -r requirements.txt
	npm install

test:
	$(PYTHON) -m pytest tests/unit -q
	npm test

itest:
	$(PYTHON) -m pytest tests/integration -q

check:
	$(PYTHON) -m pytest -q
	npm test

run:
	$(PYTHON) -m uvicorn sdk.server.app:app --reload --port 8000

hello:
	cd examples/hello-agent && $(PYTHON) -m uvicorn server:app --reload --port 8001

kyc:
	$(PYTHON) -m uvicorn kyc.server:app --reload --port 8001

