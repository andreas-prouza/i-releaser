# Workflow definition

## Define editable custom fields

A workflow may contain a custom json.

In a workflow definition I want to define which field in that json is editable for the user

```json
"editable_fields": [
  "{JSONPath}"
]
```

### Definition of done
* Create a new permission `edit-custom-data`
* Create an "edit" button next to  `Custom data` field in web (`webapp/templates/overview/list-deployments.html`)
* When click on "edit" button open via Swal a new window
  * That window contains all fields from the list (key: value)
  * Save button
* It should be able to edit fields, even if they do not exists in the custom data json