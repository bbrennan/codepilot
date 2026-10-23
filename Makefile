.PHONY: install serve doctor chat test demo ollama bench bench-validate

install:  ## Create .venv with all providers + dev tools
	uv sync --all-extras

serve:  ## Start the web UI (http://127.0.0.1:8765)
	uv run codepilot serve

doctor:  ## Check AWS/Bedrock (or Ollama), models, and the target repo
	uv run codepilot doctor

chat:  ## Terminal chat instead of the browser
	uv run codepilot chat

test:  ## Run codepilot's own unit tests (no AWS needed)
	uv run pytest -q

demo:  ## Try it locally for free: Ollama + the bundled demo agent
	CODEPILOT_PROVIDER=ollama CODEPILOT_REPO=$(CURDIR)/examples/demo-agent CODEPILOT_TEST_CMD="python3 -m pytest -q" \
		uv run codepilot serve

ollama:  ## Install Ollama and pull the default small local model
	# The Homebrew *formula* lacks the model runner on Intel Macs; the official app cask works.
	command -v ollama >/dev/null || brew install --cask ollama-app
	(curl -sf http://localhost:11434/api/version >/dev/null) || (ollama serve >/dev/null 2>&1 &) ; sleep 2
	ollama pull llama3.2:3b

bench:  ## Benchmark the configured model on all tasks (see docs/benchmark.md)
	uv run codepilot bench run

bench-validate:  ## Check every benchmark task fails unfixed and passes with its reference solution
	uv run codepilot bench validate
