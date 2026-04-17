.PHONY: install-dev test lint format html-check esphome-validate preview dev ci clean \
        docker-build docker-up docker-down docker-logs

install-dev:
	pip install -r server/requirements-dev.txt
	pre-commit install

test:
	pytest server/tests

lint:
	ruff check server/
	black --check server/

format:
	black server/
	ruff check --fix server/

html-check:
	html5validator --root server/static --ignore 'Property "aspect-ratio"'

esphome-validate:
	esphome config esphome/meeting-sign.yaml

preview:
	python server/render_preview.py

dev:
	python server/server.py

ci: lint test html-check esphome-validate

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	rm -rf server/__pycache__ server/tests/__pycache__ .pytest_cache
	rm -f preview.png
