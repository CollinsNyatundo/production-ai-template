# Testing Rules

Coding assistants and human developers must adhere to these testing protocols:

* **Test Coverage:** Every core service in `app/services/` and component in `app/components/` must have associated unit tests in the `tests/` folder.
* **Test Isolation:** Mock external calls (e.g. OpenAI/Anthropic APIs or Redis DB connections). Do not run tests that rely on external production API keys in normal test suites.
* **pytest Standard:** Write tests as standard Python functions prefixed with `test_` utilizing `pytest` assertions.
