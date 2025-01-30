
from jinja2 import Environment, PackageLoader, select_autoescape
from aiohttp import web
import json

env = Environment(
    loader=PackageLoader("index"),
    autoescape=select_autoescape()
)



def get_html_response(template, **kwargs) -> web.Response:
    template = env.get_template(template)
    html = template.render(kwargs)
    return web.Response(text=html, content_type='text/html')


def get_json_response(dict: {}, status: int=200) -> web.Response:
    json_body = json.dumps(dict)
    return web.Response(text=json_body, content_type='application/json', status=status)
