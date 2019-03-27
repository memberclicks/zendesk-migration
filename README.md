# zendesk-migration
A set of Python migration scripts to copy data from one ZenDesk account to another. The integration uses [Zenpy](https://github.com/facetoe/zenpy) for most API calls.

## Development
You will need the following environment variables to use this library:
* ZENDESK_SOURCE_EMAIL
* ZENDESK_SOURCE_PASSWORD
* ZENDESK_SOURCE_INSTANCE
* ZENDESK_TARGET_EMAIL
* ZENDESK_TARGET_PASSWORD
* ZENDESK_TARGET_INSTANCE

### Python Development
* Use `pipenv` to manage dependencies and the virtual environment.
* Set PIPENV_VENV_IN_PROJECT=true to put venv in project dir as a convenience.
* Create the virtualenv based on the Pipfile by running `pipenv install`
* Add a dependency by running `pipenv install <package>` 
* IntelliJ Setup:  add a Python facet to the module settings and choose the generated .venv dir as the interpreter
