# zendesk-migration
A set of Python migration scripts to copy data from one Zendesk account to another. The integration uses [Zenpy](https://github.com/facetoe/zenpy) for most API calls.

The migration is designed to be run in a Docker container since it can take some time to migrate a large number of tickets.

## Configuration
You will need the following environment variables to use this library:
* ZENDESK_SOURCE_EMAIL
* ZENDESK_SOURCE_PASSWORD
* ZENDESK_SOURCE_INSTANCE
* ZENDESK_TARGET_EMAIL
* ZENDESK_TARGET_PASSWORD
* ZENDESK_TARGET_INSTANCE

Optional environment variables
* ZENDESK_TICKET_START_TIME
* ZENDESK_TICKET_DEBUG
* ZENDESK_HELPCENTER_DOMAIN

## Docker Runtime
```
docker run -d --name zendesk-migration -e "ZENDESK_SOURCE_EMAIL=<>" -e "ZENDESK_SOURCE_PASSWORD=<>" -e "ZENDESK_SOURCE_INSTANCE=<>" 
-e "ZENDESK_TARGET_PASSWORD=<>" -e "ZENDESK_TARGET_EMAIL=<>" -e "ZENDESK_TARGET_INSTANCE=<>" 
-e "ZENDESK_TICKET_START_TIME=1262304000" <image>
```

By default the docker run will execute the ticket_migration.py script, but the user can override it by adding
`python script_to_run` to the end of the docker run command. 

### Python Development
* Use `pipenv` to manage dependencies and the virtual environment.
* Set PIPENV_VENV_IN_PROJECT=true to put venv in project dir as a convenience.
* Create the virtualenv based on the Pipfile by running `pipenv install`
* Add a dependency by running `pipenv install <package>` 
* IntelliJ Setup:  add a Python facet to the module settings and choose the generated .venv dir as the interpreter
