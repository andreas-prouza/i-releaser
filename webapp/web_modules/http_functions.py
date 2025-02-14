
from jinja2 import Environment, PackageLoader, select_autoescape

import json

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


#env = Environment(
#  loader=PackageLoader("webapp"),
#  autoescape=select_autoescape()
#)
templates = Jinja2Templates(directory="templates")



def get_html_response(request: Request, template: str, **kwargs) -> HTMLResponse:
    #template = env.get_template(template)
    #html = template.render(kwargs)
    html = templates.TemplateResponse(
        request=request, name=template, context={**kwargs}
    )
    return html#Response(content=html, media_type='text/html'


def get_json_response(dict: {}, status: int=200) -> JSONResponse:
    #json_body = json.dumps(dict)
    #return Response(content=json_body, media_type='application/json', status_code=status)
    return JSONResponse(content=dict, status_code=status)
