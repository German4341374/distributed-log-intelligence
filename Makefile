.PHONY: setup format lint test build demo benchmark docker clean

setup:
	uv sync --locked --extra dev

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy src benchmarks

test:
	uv run pytest

build:
	uv build

demo:
	uv run dli generate-demo demo.jsonl --lines 10000
	uv run dli analyze demo.jsonl --output report.html

benchmark:
	uv run python benchmarks/run_benchmark.py --sizes 10000 50000 200000 --repeats 3

docker:
	docker build --target runtime --tag distributed-log-intelligence:0.1.0 .

clean:
	uv run python scripts/clean.py

