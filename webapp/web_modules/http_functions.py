
import json, logging, os
from datetime import datetime, date
import decimal
from typing import Union

from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates



class DateEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()  # or any other format you prefer
        if isinstance(o, date):
            return o.isoformat()  # or any other format you prefer
        if isinstance(o, decimal.Decimal):
            return float(o)  # or any other format you prefer
        try:
            return super().default(o)
        except TypeError as e:
            logging.error(f"Error in DateEncoder: {e}; obj: {o}; type(obj): {type(o)}")
            return str(o)



def get_json_response_error(error_message: Union[str, dict, list], error_status:str = 'error', status: int=500) -> JSONResponse:

    content = json.loads(json.dumps({
        "status": error_status,
        "message": error_message
    }, cls=DateEncoder))
    
    return JSONResponse(content=content, status_code=status)




def get_json_response(dict: Union[dict, list], status: int=200) -> JSONResponse:

    content = json.loads(json.dumps(dict, cls=DateEncoder))
    
    return JSONResponse(content=content, status_code=status)




def get_html_response(request: Request, template: str, **kwargs) -> HTMLResponse:

    service_path = os.getenv("I_RELEASER_WEBAPP_PATH", "")
    if len(service_path) > 0:
        service_path += '/'

    def format_json(value):
        return json.dumps(value, indent=4)

    templates = Jinja2Templates(directory=f"{service_path}templates")
    templates.env.filters["pretty_json"] = format_json
    templates.env.filters["get_type"] = lambda v: type(v).__name__

    return templates.TemplateResponse(
        request=request, name=template, context={**kwargs, "now": datetime.now()}
    )


