from fastapi import  Request
import logging
from index import app




async def custom_test(request: Request, test: str, ):
    logging.info(f"Received test request with parameter: {test}")
    return {"message": f"Custom test successful! Received parameter: {test}"}



app.add_api_route('/custom_test/{test}', custom_test, methods=['GET'])