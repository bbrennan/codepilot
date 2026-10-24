# Let uv trust the OS certificate store (macOS Keychain), so it works behind TLS-inspecting company proxies.
# uv >= 0.11 calls this UV_SYSTEM_CERTS and warns about the older UV_NATIVE_TLS, so set only the one this uv knows.
UV_VERSION := $(shell uv --version 2>/dev/null | awk '{split($$2, v, "."); print v[1] * 1000 + v[2]}')
ifeq ($(shell [ "$(UV_VERSION)" -ge 11 ] 2>/dev/null && echo new),new)
export UV_SYSTEM_CERTS ?= true
else
export UV_NATIVE_TLS ?= true
endif

.PHONY: install serve start stop restart app doctor chat test e2e e2e-setup demo ollama bench bench-validate

install:  ## Create .venv with all providers + unit-test tools (browser-test tools install only with make e2e)
	uv sync --extra anthropic --extra openai --extra dev

serve:  ## Start the web UI (http://127.0.0.1:8765)
	uv run codepilot serve

start:  ## Run the web UI in the background (no terminal needed) and open it
	uv run codepilot start

stop:  ## Stop the background server
	uv run codepilot stop

restart:  ## Restart the background server (after git pull / make install) and open it
	uv run codepilot restart

app:  ## macOS: install ~/Applications/Codepilot.app (double-click to start and open)
	uv run codepilot app

doctor:  ## Check AWS/Bedrock (or Ollama), models, and the target repo
	uv run codepilot doctor

chat:  ## Terminal chat instead of the browser
	uv run codepilot chat

test:  ## Run codepilot's own unit tests (no AWS needed)
	uv run pytest -q

e2e-setup:  ## One-time: install Playwright and the Chromium that the browser tests drive
	uv run --extra e2e playwright install chromium

e2e:  ## Browser tests: drive the real UI end to end (no AWS needed; see tests/e2e)
	uv run --extra e2e pytest -q -m e2e tests/e2e

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
